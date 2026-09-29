"""MVP-018E: typed Nov recall against a point-in-time local Memoria.ia V2 copy.

Offline/shadow only: genuine V2 validates the incremental journal and rehydrates
EvidenceCore. This module never opens production SQLite for writing, changes a
checkpoint, connects to central services, or participates in world decisions.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sqlite3
import tempfile
from typing import Any

SOURCE_NAME = "external-episodes.sqlite3"
CHECKPOINT_SCHEMA = "live-infinita-nov-local-memory-checkpoint/v1"
SCHEMA = "live-infinita-nov-local-recall-shadow/v1"
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_WORLD_BYTES = 1_048_576
MAX_CHECKPOINT_BYTES = 8192
HEX = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = ("need", "region_id", "period", "weather", "target_entity_id", "strategy_id")


class RecallBlocked(ValueError):
    pass


def _read_bounded_json(path: Path, maximum: int, error: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink():
        raise RecallBlocked(error + "_symlink")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise RecallBlocked(error + "_oversized")
    try:
        obj = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise RecallBlocked(error + "_invalid") from exc
    if not isinstance(obj, dict):
        raise RecallBlocked(error + "_invalid")
    return raw, obj


def _world(path: Path) -> tuple[str, dict[str, Any]]:
    _, obj = _read_bounded_json(path, MAX_WORLD_BYTES, "world")
    world_id = obj.get("world_id")
    if not isinstance(world_id, str) or not 1 <= len(world_id) <= 160:
        raise RecallBlocked("world_identity_invalid")
    if not all(c.isascii() and (c.isalnum() or c in "._:-") for c in world_id):
        raise RecallBlocked("world_identity_invalid")
    return world_id, obj.get("environment") if isinstance(obj.get("environment"), dict) else {}


def _checkpoint(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw, obj = _read_bounded_json(path, MAX_CHECKPOINT_BYTES, "checkpoint")
    if obj.get("schema") != CHECKPOINT_SCHEMA:
        raise RecallBlocked("checkpoint_schema")
    cursor = obj.get("cursor")
    if type(cursor) is not int or cursor < 0:
        raise RecallBlocked("checkpoint_cursor")
    if cursor:
        for name in ("last_acked_record_key", "last_acked_content_sha256"):
            value = obj.get(name)
            if not isinstance(value, str) or HEX.fullmatch(value) is None:
                raise RecallBlocked("checkpoint_identity")
    return raw, obj


def _snapshot(source: Path, target: Path) -> int:
    if source.is_symlink() or source.name != SOURCE_NAME or not source.is_file():
        raise RecallBlocked("source_invalid")
    size = sum(
        Path(str(source) + suffix).stat().st_size
        for suffix in ("", "-wal", "-shm") if Path(str(source) + suffix).exists()
    )
    if size > MAX_SOURCE_BYTES:
        raise RecallBlocked("source_budget")
    if shutil.disk_usage(target.parent).free < 2 * MAX_SOURCE_BYTES:
        raise RecallBlocked("snapshot_space")
    before_inode = source.stat().st_ino
    src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        src.execute("PRAGMA query_only=ON")
        dest = sqlite3.connect(target, timeout=10)
        try:
            src.backup(dest, pages=64, sleep=0.05)
            if dest.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RecallBlocked("snapshot_integrity")
        finally:
            dest.close()
    finally:
        src.close()
    os.chmod(target, 0o600)
    if source.stat().st_ino != before_inode:
        raise RecallBlocked("source_inode_changed")
    return target.stat().st_size


def _confirmed_in_snapshot(snapshot: Path, checkpoint: dict[str, Any], world_id: str) -> None:
    if checkpoint.get("world_id") != world_id:
        raise RecallBlocked("checkpoint_world_mismatch")
    if checkpoint["cursor"] == 0:
        return
    conn = sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        row = conn.execute(
            "SELECT content_sha256 FROM observations WHERE record_key=?",
            (checkpoint["last_acked_record_key"],),
        ).fetchone()
        if row != (checkpoint["last_acked_content_sha256"],):
            raise RecallBlocked("checkpoint_missing_from_snapshot")
    finally:
        conn.close()


def _address_view(observation: dict[str, Any]) -> dict[str, str]:
    context = observation.get("context")
    if not isinstance(context, dict):
        context = {}
    result = {}
    for field in FIELDS:
        value = context.get(field) if field in ("region_id", "period", "weather") else observation.get(field)
        if isinstance(value, str) and value:
            result[field] = value
    return result


def select_related(records: list[dict[str, Any]], *, query: dict[str, str],
                   exclude_key: str | None, limit: int) -> tuple[list[dict[str, Any]], int]:
    """Address intersection, then recency. No text embedding, fabricated facts or action vote."""
    if type(limit) is not int or not 1 <= limit <= 8:
        raise RecallBlocked("invalid_limit")
    if not query or not set(query).issubset(FIELDS):
        raise RecallBlocked("invalid_query")
    if not all(isinstance(v, str) and v for v in query.values()):
        raise RecallBlocked("invalid_query")
    matched = []
    for record in records:
        if record["record_key"] == exclude_key:
            continue
        intersection = sorted(
            key for key, value in query.items() if record["addresses"].get(key) == value
        )
        if not intersection:
            continue
        matched.append({**record, "matching_addresses": tuple(intersection)})
    matched.sort(key=lambda row: (
        -len(row["matching_addresses"]), -row["logical_tick"], row["record_key"],
    ))
    return matched[:limit], len(matched)


def recall_once(*, source: Path, world_path: Path, checkpoint_path: Path,
                private_root: Path, need: str | None = None,
                limit: int = 5, include_evidence: bool = False,
                include_index: bool = False,
                scratch_root: Path | None = None) -> dict[str, Any]:
    """Only owner-side scratch is writable; original journal and world remain read-only."""
    if type(include_evidence) is not bool or type(include_index) is not bool:
        raise RecallBlocked("invalid_evidence_mode")
    # Imports are deliberately inside the function: this is the exact deployed
    # Memoria.ia V2, not a mock graph or a second SQLite inference backend.
    from memoria_resolutiva.external_episode_contract import ExternalEpisodeRequest
    from memoria_resolutiva.external_episode_incremental import (
        IncrementalExternalEpisodeStore, validated_payload,
    )

    world_id, environment = _world(world_path)
    before_checkpoint, watermark = _checkpoint(checkpoint_path)
    if source.is_symlink() or private_root.is_symlink() or not private_root.is_dir():
        raise RecallBlocked("private_source_invalid")
    if source.parent.parent != private_root:
        raise RecallBlocked("source_root_mismatch")
    # systemd may mount the private source read-only. A separate explicit
    # service-owner-only scratch dir holds backup and V2 rehydration.
    scratch = private_root
    if scratch_root is not None:
        if (not isinstance(scratch_root, Path) or not scratch_root.is_absolute()
                or scratch_root.is_symlink() or not scratch_root.is_dir()):
            raise RecallBlocked("snapshot_scratch_invalid")
        info = scratch_root.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise RecallBlocked("snapshot_scratch_permissions")
        if scratch_root.resolve().is_relative_to(private_root.resolve()):
            raise RecallBlocked("snapshot_scratch_in_private_root")
        scratch = scratch_root
    with tempfile.TemporaryDirectory(prefix="nov-recall-", dir=scratch) as tmp:
        root = Path(tmp)
        os.chmod(root, 0o700)
        snapshot = root / SOURCE_NAME
        snapshot_bytes = _snapshot(source, snapshot)
        _confirmed_in_snapshot(snapshot, watermark, world_id)
        store = IncrementalExternalEpisodeStore(root)
        try:
            edges = {edge.evidence_id: edge for edge in store.core._edges}
            if len(edges) != store.count:
                raise RecallBlocked("evidence_graph_count_mismatch")
            records: list[dict[str, Any]] = []
            rows = store._db.execute(
                "SELECT record_key,content_sha256,source_json,evidence_id,world_id,"
                "episode_id,logical_tick FROM observations ORDER BY rowid"
            )
            for key, digest, source_json, evidence_id, source_world, episode_id, tick in rows:
                if not isinstance(source_json, str):
                    raise RecallBlocked("source_payload_invalid")
                unsigned = json.loads(source_json)
                request = ExternalEpisodeRequest.model_validate({
                    **unsigned, "content_sha256": digest,
                })
                actual_key, payload, actual_digest, actual_evidence = validated_payload(request)
                if (key != actual_key or digest != actual_digest or evidence_id != actual_evidence
                        or source_json != payload.decode("utf-8")
                        or source_world != request.source.world_id
                        or episode_id != request.source.episode_id
                        or tick != request.observation.logical_tick):
                    raise RecallBlocked("typed_provenance_mismatch")
                edge = edges.get(evidence_id)
                if (edge is None or edge.source_text != source_json
                        or edge.predicate != "observed_experience"
                        or edge.subject != "live:episode:" + evidence_id
                        or edge.object != "live:entity:" + source_world + ":nov"
                        or edge.namespace != "live:" + source_world
                        or edge.origin != "live.infinita:" + source_world
                        or edge.provenance != "live.infinita:npc_episode_v1"
                        or edge.epoch != tick or edge.confidence != 1.0):
                    raise RecallBlocked("evidence_provenance_mismatch")
                if source_world == world_id and request.source.entity_id == "nov":
                    records.append({
                        "record_key": key, "evidence_id": evidence_id,
                        "content_sha256": digest, "logical_tick": tick,
                        "addresses": _address_view(request.observation.model_dump(mode="json")),
                        "observation": request.observation.model_dump(mode="json"),
                    })
            if len(records) > 100_000:
                raise RecallBlocked("record_budget")
            records.sort(key=lambda row: (row["logical_tick"], row["record_key"]))
            if need is not None and (not isinstance(need, str) or not 1 <= len(need) <= 96):
                raise RecallBlocked("invalid_need")
            exclude = None
            if need:
                query = {"need": need}
                for field in ("period", "weather"):
                    value = environment.get(field)
                    if isinstance(value, str) and value:
                        query[field] = value
                basis = "explicit_need_and_live_environment"
            elif records:
                seed = records[-1]
                query = dict(seed["addresses"])
                exclude = seed["record_key"]
                basis = "latest_confirmed_episode"
            else:
                query = {}
                basis = "memory_empty"
            if query:
                selected, matching = select_related(
                    records, query=query, exclude_key=exclude, limit=limit,
                )
            else:
                selected, matching = [], 0
            count = store.count
        finally:
            store.close()
        after_checkpoint, _ = _checkpoint(checkpoint_path)
        if _world(world_path)[0] != world_id:
            raise RecallBlocked("world_identity_changed")
        # Future read-only consumers may request typed evidence in-process;
        # the operator CLI never enables this sensitive field.
        result = {
            "schema": SCHEMA, "mode": "read-only-shadow",
            "world_identity_validated": True,
            "source_backend": "sqlite-incremental",
            "source_snapshot_records": count,
            "snapshot_bytes": snapshot_bytes,
            "nov_observations": len(records),
            "query_basis": basis,
            "query_address_count": len(query),
            "historical_matches": matching,
            "selected": [{
                "logical_tick": row["logical_tick"],
                "matched_address_count": len(row["matching_addresses"]),
                "source": "typed_confirmed_nov_outcome",
            } for row in selected],
            "checkpoint_watermark_in_snapshot": True,
            "checkpoint_unchanged_during_copy": before_checkpoint == after_checkpoint,
            "bdr_used": False,
            "world_mutated": False,
            "selection_authority": False,
            "central_sync": False,
            "live_caught_up_claim": False,
        }
        if include_evidence:
            result["private_evidence"] = [{
                "record_key": row["record_key"],
                "evidence_id": row["evidence_id"],
                "content_sha256": row["content_sha256"],
                "logical_tick": row["logical_tick"],
                "observation": row["observation"],
                "matching_addresses": list(row["matching_addresses"]),
                "provenance": "live.infinita:npc_episode_v1",
                "world_id": world_id,
            } for row in selected]
        if include_index:
            # Privileged, in-process cache seed. Never enabled by the operator
            # command, serialized, logged or persisted. Each record was checked
            # against the genuine rehydrated V2 EvidenceCore above.
            result["_private_index"] = records
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--need", default=None)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        result = recall_once(
            source=args.source, world_path=args.world, checkpoint_path=args.checkpoint,
            private_root=args.private_root, need=args.need, limit=args.limit,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise SystemExit("MVP018E_NOV_RECALL_BLOCKED " + type(exc).__name__ + ": " +
                         (str(exc) if isinstance(exc, RecallBlocked) else "validation_failed")) from exc
    print("MVP018E_NOV_RECALL_SHADOW_OK " +
          json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
