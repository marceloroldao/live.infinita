"""Bounded, owner-only read-through cache for genuine Memoria.ia V2 Nov recall.

One V2-validated SQLite/WAL snapshot is loaded into process memory; later frame
queries reuse its typed index. Checkpoint, DB and WAL changes invalidate it.
This is an optional provider for Shadow Mode, never a production service.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from threading import RLock
from time import monotonic
from typing import Any, Callable

from memoria_v2_adapter import CognitiveFrame
from nov_memory_recall_shadow import (
    CHECKPOINT_SCHEMA, SOURCE_NAME, SCHEMA, RecallBlocked,
    _checkpoint, _world, recall_once, select_related,
)

MAX_CACHE_RECORDS = 2048
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_CACHE_AGE_SECONDS = 180.0
MAX_SELECTION = 5


@dataclass(frozen=True, slots=True)
class SourceVersion:
    world_id: str
    checkpoint_sha256: str
    db: tuple[int, int, int, int]
    wal: tuple[int, int, int, int] | None


def _regular_signature(path: Path, *, optional: bool = False) -> tuple[int, int, int, int] | None:
    if path.is_symlink():
        raise RecallBlocked("version_symlink")
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        if optional:
            return None
        raise RecallBlocked("version_source_missing") from None
    if not stat.S_ISREG(info.st_mode):
        raise RecallBlocked("version_source_not_regular")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def frame_world(frame: CognitiveFrame) -> str:
    if frame.observer_id != "nov" or type(frame.tick_id) is not int or frame.tick_id < 0:
        raise RecallBlocked("invalid_nov_frame")
    values = [
        address.removeprefix("live:world:")
        for address in frame.state_addresses
        if isinstance(address, str) and address.startswith("live:world:")
    ]
    if len(values) != 1 or not values[0]:
        raise RecallBlocked("frame_world_unavailable")
    return values[0]


def frame_query(frame: CognitiveFrame, seed: dict[str, Any]) -> dict[str, str]:
    """Only current frame location/weather/period and a confirmed seed need."""
    addresses = seed.get("addresses")
    if not isinstance(addresses, dict):
        raise RecallBlocked("invalid_seed_addresses")
    query = {}
    need = addresses.get("need")
    if isinstance(need, str) and need:
        query["need"] = need
    for field in ("region_id", "weather", "period"):
        namespace = "region" if field == "region_id" else field
        prefix = "live:" + namespace + ":"
        values = [
            address[len(prefix):] for address in frame.state_addresses
            if isinstance(address, str) and address.startswith(prefix)
        ]
        if len(values) > 1:
            raise RecallBlocked("ambiguous_frame_address")
        if values and values[0]:
            query[field] = values[0]
    return query


@dataclass(slots=True, repr=False)
class VersionedNovRecallCache:
    """No disk cache, background thread, central network or per-tick V2 rebuild."""

    source: Path
    world_path: Path
    checkpoint_path: Path
    private_root: Path
    max_age_seconds: float = MAX_CACHE_AGE_SECONDS
    max_records: int = MAX_CACHE_RECORDS
    max_index_bytes: int = MAX_CACHE_BYTES
    _clock: Callable[[], float] = field(default=monotonic, repr=False)
    _loader: Callable[..., dict[str, Any]] = field(default=recall_once, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _version_loaded: SourceVersion | None = field(default=None, init=False, repr=False)
    _validated_index: tuple[dict[str, Any], ...] = field(default=(), init=False, repr=False)
    _report: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _loaded_at: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if (type(self.max_age_seconds) not in (float, int)
                or not 1 <= self.max_age_seconds <= 3600):
            raise RecallBlocked("invalid_cache_age")
        if type(self.max_records) is not int or not 1 <= self.max_records <= MAX_CACHE_RECORDS:
            raise RecallBlocked("invalid_cache_record_budget")
        if type(self.max_index_bytes) is not int or not 1024 <= self.max_index_bytes <= MAX_CACHE_BYTES:
            raise RecallBlocked("invalid_cache_byte_budget")
        if self.source.name != SOURCE_NAME or self.source.parent.parent != self.private_root:
            raise RecallBlocked("cache_source_root_mismatch")

    def invalidate(self) -> None:
        with self._lock:
            self._version_loaded = None
            self._report = None
            self._validated_index = ()

    def _current_version(self) -> SourceVersion:
        if self.source.is_symlink() or self.private_root.is_symlink():
            raise RecallBlocked("cache_private_path_invalid")
        world_id, _ = _world(self.world_path)
        checkpoint_bytes, checkpoint = _checkpoint(self.checkpoint_path)
        if checkpoint.get("schema") != CHECKPOINT_SCHEMA or checkpoint.get("world_id") != world_id:
            raise RecallBlocked("cache_checkpoint_world_mismatch")
        return SourceVersion(
            world_id=world_id,
            checkpoint_sha256=sha256(checkpoint_bytes).hexdigest(),
            db=_regular_signature(self.source),
            wal=_regular_signature(Path(str(self.source) + "-wal"), optional=True),
        )

    def _load(self, version: SourceVersion) -> None:
        self.invalidate()
        result = self._loader(
            source=self.source,
            world_path=self.world_path,
            checkpoint_path=self.checkpoint_path,
            private_root=self.private_root,
            include_index=True,
            include_evidence=False,
        )
        if (not isinstance(result, dict) or result.get("schema") != SCHEMA
                or result.get("source_backend") != "sqlite-incremental"
                or result.get("world_identity_validated") is not True
                or result.get("checkpoint_watermark_in_snapshot") is not True
                or result.get("checkpoint_unchanged_during_copy") is not True
                or result.get("world_mutated") is not False
                or result.get("selection_authority") is not False
                or result.get("central_sync") is not False or result.get("bdr_used") is not False):
            raise RecallBlocked("cache_unverified_snapshot")
        rows = result.get("_private_index")
        total = result.get("source_snapshot_records")
        nov_total = result.get("nov_observations")
        if (not isinstance(rows, list) or type(total) is not int or type(nov_total) is not int
                or total < nov_total or len(rows) != nov_total
                or len(rows) > self.max_records):
            raise RecallBlocked("cache_record_budget_or_count")
        total_bytes = sum(
            len(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
            for row in rows
        )
        if total_bytes > self.max_index_bytes:
            raise RecallBlocked("cache_byte_budget")
        if version != self._current_version():
            raise RecallBlocked("cache_source_moved_during_load")
        self._validated_index = tuple(rows)
        self._report = {key: value for key, value in result.items()
                        if key != "_private_index" and key != "private_evidence"}
        self._version_loaded = version
        self._loaded_at = self._clock()

    def __call__(self, frame: CognitiveFrame) -> dict[str, Any]:
        """Match a current frame to prior typed evidence (caller must keep private)."""
        with self._lock:
            wanted_world = frame_world(frame)
            before = self._current_version()
            if before.world_id != wanted_world:
                self.invalidate()
                raise RecallBlocked("cache_frame_world_mismatch")
            now = self._clock()
            needs_refresh = (
                self._version_loaded != before or self._report is None
                or now - self._loaded_at >= self.max_age_seconds
                or now < self._loaded_at
            )
            if needs_refresh:
                self._load(before)
            assert self._report is not None
            eligible = [
                row for row in self._validated_index
                if type(row.get("logical_tick")) is int
                and row["logical_tick"] <= frame.tick_id
            ]
            if eligible:
                seed = max(eligible, key=lambda row: (row["logical_tick"], row["record_key"]))
                query = frame_query(frame, seed)
                if query:
                    selected, total_matches = select_related(
                        eligible, query=query, exclude_key=seed["record_key"],
                        limit=MAX_SELECTION,
                    )
                else:
                    selected, total_matches = [], 0
                basis = "latest_confirmed_need_plus_current_frame"
            else:
                query, selected, total_matches = {}, [], 0
                basis = "no_confirmed_past_at_frame_tick"

            result = {
                "schema": SCHEMA,
                "mode": "read-only-shadow",
                "source_backend": "sqlite-incremental",
                "source_snapshot_records": self._report["source_snapshot_records"],
                "nov_observations": len(eligible),
                "query_basis": basis,
                "query_address_count": len(query),
                "historical_matches": total_matches,
                "selected": [{
                    "logical_tick": row["logical_tick"],
                    "matched_address_count": len(row["matching_addresses"]),
                    "source": "typed_confirmed_nov_outcome",
                } for row in selected],
                "private_evidence": [{
                    "record_key": row["record_key"],
                    "evidence_id": row["evidence_id"],
                    "content_sha256": row["content_sha256"],
                    "logical_tick": row["logical_tick"],
                    "observation": deepcopy(row["observation"]),
                    "matching_addresses": list(row["matching_addresses"]),
                    "provenance": "live.infinita:npc_episode_v1",
                    "world_id": wanted_world,
                } for row in selected],
                "world_identity_validated": True,
                "checkpoint_watermark_in_snapshot": True,
                "checkpoint_unchanged_during_copy": True,
                "world_mutated": False,
                "selection_authority": False,
                "central_sync": False,
                "bdr_used": False,
                "live_caught_up_claim": False,
                "cache_status": "refreshed" if needs_refresh else "hit",
            }
            if self._current_version() != before:
                self.invalidate()
                raise RecallBlocked("cache_source_moved_during_query")
            return result
