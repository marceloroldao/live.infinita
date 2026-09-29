"""Typed, read-only export preview of confirmed Nov outcomes.

This is NOT an HTTP transport or an acknowledgment ledger. It cannot send to
Memoria.ia, advance a durable cursor, or modify the autonomous World State.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import os
from typing import Any

from packages.observability.nov_life import project_confirmed_episode

SCHEMA = "live-infinita-npc-episode-observation/v1"
BATCH_SCHEMA = "live-infinita-npc-episode-preview/v1"
MAX_BATCH_BYTES = 262_144
MAX_BATCH_RECORDS = 16
MAX_WORLD_META_BYTES = 1_048_576


class EpisodeSyncContractError(ValueError):
    """The preview cannot safely advance. No checkpoint or receipt is emitted."""


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _source_identifier(value: Any, *, maximum: int = 160) -> str | None:
    if not isinstance(value, str) or not (0 < len(value) <= maximum):
        return None
    if not all(c.isascii() and (c.isalnum() or c in "._:-") for c in value):
        return None
    return value


def world_identity(world_path: Path) -> str:
    """Read only bounded authoritative metadata, never reconstruct a world."""
    try:
        with Path(world_path).open("rb") as source:
            stat = source.seek(0, 2)
            if stat > MAX_WORLD_META_BYTES:
                raise EpisodeSyncContractError("world_metadata_exceeds_limit")
            source.seek(0)
            world = json.loads(source.read(MAX_WORLD_META_BYTES + 1))
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, EpisodeSyncContractError):
            raise
        raise EpisodeSyncContractError("world_identity_unavailable") from exc
    if not isinstance(world, dict):
        raise EpisodeSyncContractError("world_identity_unavailable")
    world_id = _source_identifier(world.get("world_id"))
    if world_id is None:
        raise EpisodeSyncContractError("invalid_world_identity")
    return world_id


def observation_envelope(row: dict[str, Any], *, world_id: str) -> dict[str, Any] | None:
    """Preserve only verified outcome data; do not invent language or source."""
    world_id = _source_identifier(world_id)
    if world_id is None:
        raise EpisodeSyncContractError("invalid_world_identity")
    if not isinstance(row, dict) or row.get("npc_id") != "nov":
        return None
    if row.get("episode_schema") != "npc_episode_v1":
        return None
    if any(field in row for field in ("role", "text", "narration", "llm_generated")):
        raise EpisodeSyncContractError("mixed_conversation_provenance")
    episode = project_confirmed_episode(row)
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    plan_id = _source_identifier(source.get("plan_id"))
    proposal_id = _source_identifier(source.get("proposal_id"))
    revision = source.get("plan_revision")
    if (episode is None or source.get("kind") != "need_outcome" or plan_id is None
            or episode["episode_id"] != "plan:" + plan_id or proposal_id is None
            or isinstance(revision, bool) or not isinstance(revision, int)
            or not (0 <= revision <= 1_000_000)):
        # A conversation, shadow forecast, or partially proven source is not
        # a confirmed, typed agent experience eligible for central transport.
        raise EpisodeSyncContractError("episode_provenance_not_confirmed")
    source_identity = {
        "system": "live.infinita",
        "world_id": world_id,
        "entity_id": "nov",
        "episode_id": episode["episode_id"],
        "source_schema": "npc_episode_v1",
        "source_kind": "need_outcome",
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "plan_revision": revision,
    }
    record_key = sha256(_canonical_bytes({
        "system": "live.infinita", "world_id": world_id,
        "entity_id": "nov", "episode_id": episode["episode_id"],
    })).hexdigest()
    observation = {
        "logical_tick": episode["logical_tick"],
        "need": episode["need"],
        "target_entity_id": episode["target_entity_id"],
        "strategy_id": episode["strategy_id"],
        "context": episode["context"],
        "outcome": episode["outcome"],
    }
    unsigned = {
        "schema": SCHEMA,
        "record_key": record_key,
        "source": source_identity,
        "observation": observation,
        "authority": "observed-outcome-only",
        "world_write_authority": False,
    }
    return {**unsigned, "content_sha256": sha256(_canonical_bytes(unsigned)).hexdigest()}


def preview_episode_batch(
    episode_file: Path, world_file: Path, *,
    cursor: int = 0, max_bytes: int = MAX_BATCH_BYTES,
    limit: int = 8,
) -> dict[str, Any]:
    """Bounded byte-offset pagination. A candidate cursor is NOT an ACK."""
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise EpisodeSyncContractError("invalid_cursor")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise EpisodeSyncContractError("invalid_max_bytes")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise EpisodeSyncContractError("invalid_limit")
    max_bytes = max(1, min(max_bytes, MAX_BATCH_BYTES))
    limit = max(1, min(limit, MAX_BATCH_RECORDS))
    world_id = world_identity(world_file)
    episodes: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    examined = 0
    candidate_cursor = cursor
    partial_tail = False
    try:
        with Path(episode_file).open("rb") as source:
            info = source.seek(0, 2)
            if cursor > info:
                raise EpisodeSyncContractError("cursor_beyond_ledger")
            if cursor:
                source.seek(cursor - 1)
                if source.read(1) != b"\n":
                    raise EpisodeSyncContractError("cursor_not_line_boundary")
            source.seek(cursor)
            data = source.read(min(max_bytes, info - cursor))
            stat_result = os.fstat(source.fileno())
            identity = f"{stat_result.st_dev}:{stat_result.st_ino}"
    except OSError as exc:
        raise EpisodeSyncContractError("episode_ledger_unavailable") from exc
    at = 0
    for raw_line in data.splitlines(keepends=True):
        if not raw_line.endswith(b"\n"):
            partial_tail = True
            break
        # Each consumed record is complete, including its newline. Malformed
        # rows stop the preview instead of silently committing over corruption.
        try:
            row = json.loads(raw_line)
        except (ValueError, UnicodeError) as exc:
            raise EpisodeSyncContractError("malformed_episode_record") from exc
        if not isinstance(row, dict):
            raise EpisodeSyncContractError("malformed_episode_record")
        examined += 1
        at += len(raw_line)
        candidate_cursor = cursor + at
        envelope = observation_envelope(row, world_id=world_id)
        if envelope is not None:
            key = envelope["record_key"]
            digest = envelope["content_sha256"]
            if key in seen and seen[key] != digest:
                raise EpisodeSyncContractError("conflicting_episode_identity")
            if key not in seen:
                seen[key] = digest
                episodes.append(envelope)
        if len(episodes) >= limit:
            break
    if data and candidate_cursor == cursor and b"\n" not in data and len(data) == max_bytes:
        raise EpisodeSyncContractError("episode_line_exceeds_window")
    return {
        "schema": BATCH_SCHEMA,
        "mode": "read-only-transport-preview",
        "world_id": world_id,
        "observer_id": "nov",
        "ledger_identity": identity,
        "ledger_size_at_read": info,
        "input_cursor": cursor,
        "candidate_next_cursor": candidate_cursor,
        "candidate_cursor_is_ack": False,
        "rows_examined": examined,
        "episodes": episodes,
        "more_bytes_after_candidate_cursor": candidate_cursor < info,
        "partial_tail": partial_tail,
        "transport_enabled": False,
        "central_receipt": None,
        "world_mutated": False,
        "selection_authority": False,
    }
