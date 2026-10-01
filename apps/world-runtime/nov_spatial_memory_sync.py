"""Incrementally mirror confirmed Nov movement into Memoria.ia structural memory.

The authoritative source remains deltas.jsonl. Only accepted, already-committed
Nov move operations are projected. The bridge never writes World State and only
advances its checkpoint after Memoria.ia durably acknowledges a structural
observation. Replays are idempotent because event identity is content-derived.
"""
from __future__ import annotations

import argparse
from hashlib import blake2b, sha256
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path("/var/lib/live-infinita/autonomous-world")
MEMORY_ROOT = Path("/var/lib/live-infinita/memoria-local")
DELTA_PATH = ROOT / "deltas.jsonl"
WORLD_PATH = ROOT / "world.json"
CHECKPOINT_PATH = MEMORY_ROOT / "nov-spatial-ingest.checkpoint.json"
ENDPOINT = "http://127.0.0.1:8788/api/v1/structural/observations"

CHECKPOINT_SCHEMA = "live-infinita-nov-spatial-checkpoint/v1"
HIERARCHY_PREFIX = "live:spatial:"
RESOLUTION_M = 4.0
MAX_LINE_BYTES = 262_144
MAX_WINDOW_BYTES = 512 * 1024
MAX_EVENTS_PER_RUN = 2
MOVES_PER_EVENT = 12
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class SpatialMemorySyncError(RuntimeError):
    pass
def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _world_id(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise SpatialMemorySyncError("world_identity_unavailable") from exc
    world_id = str(value.get("world_id") or "").strip() if isinstance(value, dict) else ""
    if not world_id or len(world_id) > 160:
        raise SpatialMemorySyncError("world_identity_invalid")
    return world_id


def _ledger_identity(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError as exc:
        raise SpatialMemorySyncError("delta_ledger_unavailable") from exc
    return f"{stat.st_dev}:{stat.st_ino}"


def _line_digest_at_cursor(path: Path, cursor: int) -> str | None:
    if cursor == 0:
        return None
    with path.open("rb") as fh:
        if fh.seek(0, os.SEEK_END) < cursor:
            raise SpatialMemorySyncError("delta_ledger_truncated")
        fh.seek(cursor - 1)
        if fh.read(1) != b"\n":
            raise SpatialMemorySyncError("checkpoint_not_line_boundary")
        start = max(0, cursor - MAX_LINE_BYTES)
        fh.seek(start)
        data = fh.read(cursor - start)
    previous = data[:-1].rfind(b"\n")
    if start and previous < 0:
        raise SpatialMemorySyncError("checkpoint_line_exceeds_limit")
    line = data[previous + 1:]
    if not line.endswith(b"\n"):
        raise SpatialMemorySyncError("checkpoint_line_incomplete")
    return sha256(line).hexdigest()


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise SpatialMemorySyncError("checkpoint_symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeError) as exc:
        raise SpatialMemorySyncError("checkpoint_unreadable") from exc
    if not isinstance(raw, dict) or raw.get("schema") != CHECKPOINT_SCHEMA:
        raise SpatialMemorySyncError("checkpoint_schema")
    cursor = raw.get("cursor")
    sequence = raw.get("last_sequence")
    if type(cursor) is not int or cursor < 0:
        raise SpatialMemorySyncError("checkpoint_cursor")
    if sequence is not None and (type(sequence) is not int or sequence < 0):
        raise SpatialMemorySyncError("checkpoint_sequence")
    if not isinstance(raw.get("world_id"), str) or not raw["world_id"]:
        raise SpatialMemorySyncError("checkpoint_world")
    if not isinstance(raw.get("ledger_identity"), str) or not raw["ledger_identity"]:
        raise SpatialMemorySyncError("checkpoint_ledger")
    digest = raw.get("last_line_sha256")
    if cursor == 0:
        if digest is not None:
            raise SpatialMemorySyncError("checkpoint_digest")
    elif not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise SpatialMemorySyncError("checkpoint_digest")
    pos = raw.get("last_position")
    if pos is not None:
        _position(pos)
    event_id = raw.get("last_event_id")
    if event_id is not None and (not isinstance(event_id, str) or not event_id):
        raise SpatialMemorySyncError("checkpoint_event_id")
    result_hash = raw.get("last_result_hash")
    if result_hash is not None and (not isinstance(result_hash, str) or not HEX64.fullmatch(result_hash)):
        raise SpatialMemorySyncError("checkpoint_result_hash")
    return raw
def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise SpatialMemorySyncError("checkpoint_symlink")
    encoded = _canonical(payload) + b"\n"
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _verify_checkpoint(checkpoint: dict[str, Any] | None, path: Path, world_id: str) -> None:
    if checkpoint is None:
        return
    if checkpoint["world_id"] != world_id:
        raise SpatialMemorySyncError("world_identity_changed")
    if checkpoint["ledger_identity"] != _ledger_identity(path):
        raise SpatialMemorySyncError("delta_ledger_identity_changed")
    if checkpoint["last_line_sha256"] != _line_digest_at_cursor(path, checkpoint["cursor"]):
        raise SpatialMemorySyncError("checkpoint_source_changed")


def _position(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise SpatialMemorySyncError("position_invalid")
    try:
        x, y = float(raw["x"]), float(raw["y"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SpatialMemorySyncError("position_invalid") from exc
    if not math.isfinite(x) or not math.isfinite(y) or abs(x) > 10_000_000 or abs(y) > 10_000_000:
        raise SpatialMemorySyncError("position_invalid")
    return {"x": x, "y": y}
def _zigzag(value: int) -> int:
    return value * 2 if value >= 0 else -value * 2 - 1


def _cell_id(position: dict[str, float]) -> int:
    qx = int(round(position["x"] / RESOLUTION_M))
    qy = int(round(position["y"] / RESOLUTION_M))
    a, b = _zigzag(qx), _zigzag(qy)
    total = a + b
    return total * (total + 1) // 2 + b


def _relation_id(from_region: str | None, to_region: str | None) -> int:
    value = f"{from_region or ''}->{to_region or ''}".encode("utf-8")
    return int.from_bytes(blake2b(value, digest_size=8).digest(), "big")


def _observation_id(event: dict[str, Any]) -> str:
    normalized = {
        "version": int(event["version"]),
        "source_id": str(event["source_id"]).strip(),
        "sequence": int(event["sequence"]),
        "byte_offset": int(event["byte_offset"]),
        "byte_length": int(event["byte_length"]),
        "trail": [int(v) for v in event["trail"]],
        "relation_ids": [int(v) for v in event["relation_ids"]],
        "signature": str(event["signature"]).strip().lower(),
        "resolution": int(event["resolution"]),
    }
    return "structural-event:" + blake2b(_canonical(normalized), digest_size=20).hexdigest()


def _structural_request(
    *, world_id: str, sequence: int, byte_offset: int, byte_length: int,
    event_id: str, result_hash: str, previous: dict[str, Any], current: dict[str, Any],
) -> dict[str, Any]:
    from_position = _position(previous["position"])
    to_position = _position(current["position"])
    from_region = str(previous.get("region_id") or "").strip() or None
    to_region = str(current.get("region_id") or "").strip() or None
    signature_basis = {
        "world_id": world_id,
        "sequence": sequence,
        "event_id": event_id,
        "from": from_position,
        "to": to_position,
        "from_region_id": from_region,
        "to_region_id": to_region,
        "result_hash": result_hash,
    }
    event = {
        "version": 1,
        "source_id": f"live.infinita:{world_id}:nov:movement",
        "sequence": sequence,
        "byte_offset": byte_offset,
        "byte_length": byte_length,
        "trail": [_cell_id(from_position), _cell_id(to_position)],
        "relation_ids": [_relation_id(from_region, to_region)],
        "signature": blake2b(_canonical(signature_basis), digest_size=8).hexdigest(),
        "resolution": int(RESOLUTION_M),
    }
    return {
        "event": event,
        "provenance": {
            "hierarchy_id": HIERARCHY_PREFIX + world_id + ":nov",
            "source_kind": "confirmed_world_delta_move",
            "source_ledger": "deltas.jsonl",
            "world_id": world_id,
            "entity_id": "nov",
            "authority": "observed-world-delta",
            "world_write_authority": False,
            "world_sequence": sequence,
            "world_event_id": event_id,
            "result_hash": result_hash,
            "spatial_resolution_m": RESOLUTION_M,
            "from_position": from_position,
            "to_position": to_position,
            "from_region_id": from_region,
            "to_region_id": to_region,
        },
    }


def _trajectory_request(
    *, world_id: str, previous: dict[str, Any], moves: list[dict[str, Any]],
) -> dict[str, Any]:
    if not moves:
        raise SpatialMemorySyncError("trajectory_empty")
    points = [previous] + moves
    positions = [_position(item["position"]) for item in points]
    regions = [str(item.get("region_id") or "").strip() or None for item in points]
    sequences = [int(item.get("sequence") or 0) for item in points]
    first = moves[0]
    last = moves[-1]
    byte_offset = int(first["_row_offset"])
    byte_end = int(last["_row_end"])
    if byte_end <= byte_offset:
        raise SpatialMemorySyncError("trajectory_source_span")
    trail = [_cell_id(position) for position in positions]
    relations = [
        _relation_id(regions[index], regions[index + 1])
        for index in range(len(regions) - 1)
    ]
    signature_basis = {
        "world_id": world_id,
        "sequences": sequences,
        "event_ids": [str(item.get("event_id") or "") for item in points],
        "result_hashes": [str(item.get("result_hash") or "") for item in points],
        "positions": positions,
        "regions": regions,
    }
    event = {
        "version": 1,
        "source_id": f"live.infinita:{world_id}:nov:trajectory-v2",
        "sequence": int(last["sequence"]),
        "byte_offset": byte_offset,
        "byte_length": byte_end - byte_offset,
        "trail": trail,
        "relation_ids": relations,
        "signature": blake2b(_canonical(signature_basis), digest_size=8).hexdigest(),
        "resolution": int(RESOLUTION_M),
    }
    return {
        "event": event,
        "provenance": {
            "hierarchy_id": HIERARCHY_PREFIX + world_id + ":nov:trajectory-v2",
            "source_kind": "confirmed_world_delta_trajectory",
            "source_ledger": "deltas.jsonl",
            "world_id": world_id,
            "entity_id": "nov",
            "authority": "observed-world-delta",
            "world_write_authority": False,
            "world_sequence_start": int(moves[0]["sequence"]),
            "world_sequence": int(last["sequence"]),
            "world_event_id": str(last["event_id"]),
            "result_hash": str(last["result_hash"]),
            "spatial_resolution_m": RESOLUTION_M,
            "path_positions": positions,
            "path_region_ids": regions,
            "path_sequences": sequences,
            "segment_count": len(moves),
            "from_position": positions[0],
            "to_position": positions[-1],
            "from_region_id": regions[0],
            "to_region_id": regions[-1],
        },
    }


def _checkpoint_payload(
    *, world_id: str, delta_path: Path, cursor: int, previous: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "world_id": world_id,
        "ledger_identity": _ledger_identity(delta_path),
        "cursor": cursor,
        "last_line_sha256": _line_digest_at_cursor(delta_path, cursor),
        "last_sequence": None if previous is None else previous.get("sequence"),
        "last_position": None if previous is None else previous.get("position"),
        "last_region_id": None if previous is None else previous.get("region_id"),
        "last_event_id": None if previous is None else previous.get("event_id"),
        "last_result_hash": None if previous is None else previous.get("result_hash"),
        "updated_at_unix": time.time(),
    }


def _post_local(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("MEMORIA_API_KEY", "")
    if len(api_key) < 32:
        raise SpatialMemorySyncError("local_api_key_unconfigured")
    body = _canonical(payload)
    request = Request(
        ENDPOINT, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "X-Memoria-Key": api_key},
    )
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
            raw = response.read(8193)
            if response.status != 201 or len(raw) > 8192:
                raise SpatialMemorySyncError("invalid_structural_response")
        value = json.loads(raw)
    except HTTPError as exc:
        raise SpatialMemorySyncError(f"structural_http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise SpatialMemorySyncError("structural_endpoint_unavailable") from exc
    if not isinstance(value, dict):
        raise SpatialMemorySyncError("invalid_structural_response")
    return value


def _validate_ack(response: dict[str, Any], payload: dict[str, Any]) -> None:
    expected = _observation_id(payload["event"])
    if (
        response.get("observation_id") != expected
        or not isinstance(response.get("stored"), bool)
        or not isinstance(response.get("duplicate"), bool)
        or response.get("semantic_projection") is not False
        or response.get("backend") not in {"sqlite", "bdr"}
    ):
        raise SpatialMemorySyncError("structural_ack_mismatch")


def _move_from_delta(row: dict[str, Any]) -> dict[str, Any] | None:
    operations = row.get("operations")
    if not isinstance(operations, list):
        return None
    moves = [
        op for op in operations
        if isinstance(op, dict) and op.get("op") == "move" and op.get("entity_id") == "nov"
    ]
    if not moves:
        return None
    if len(moves) != 1:
        raise SpatialMemorySyncError("multiple_nov_moves_in_delta")
    move = moves[0]
    sequence = row.get("sequence")
    event_id = str(row.get("event_id") or "").strip()
    result_hash = str(row.get("result_hash") or "").strip()
    if type(sequence) is not int or sequence < 0 or not event_id or not HEX64.fullmatch(result_hash):
        raise SpatialMemorySyncError("delta_identity_invalid")
    return {
        "sequence": sequence,
        "event_id": event_id,
        "result_hash": result_hash,
        "position": _position(move.get("position")),
        "region_id": str(move.get("region_id") or "").strip() or None,
    }


def _bootstrap_cursor(path: Path) -> int:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SpatialMemorySyncError("delta_ledger_unavailable") from exc
    if size <= MAX_WINDOW_BYTES:
        return 0
    start = size - MAX_WINDOW_BYTES
    with path.open("rb") as fh:
        fh.seek(start)
        fh.readline()  # discard a possibly partial first record
        return fh.tell()


def sync_once(
    *, delta_path: Path = DELTA_PATH, world_path: Path = WORLD_PATH,
    checkpoint_path: Path = CHECKPOINT_PATH,
    send: Callable[[dict[str, Any]], dict[str, Any]] = _post_local,
    max_events: int = MAX_EVENTS_PER_RUN,
    moves_per_event: int = MOVES_PER_EVENT,
) -> dict[str, Any]:
    max_events = max(1, min(int(max_events), MAX_EVENTS_PER_RUN))
    moves_per_event = max(1, min(int(moves_per_event), MOVES_PER_EVENT))
    world_id = _world_id(world_path)
    checkpoint = _read_checkpoint(checkpoint_path)
    _verify_checkpoint(checkpoint, delta_path, world_id)

    cursor = int(checkpoint["cursor"]) if checkpoint is not None else _bootstrap_cursor(delta_path)
    previous = None
    if checkpoint and checkpoint.get("last_position") is not None:
        previous = {
            "position": _position(checkpoint["last_position"]),
            "region_id": checkpoint.get("last_region_id"),
            "sequence": checkpoint.get("last_sequence"),
            "event_id": checkpoint.get("last_event_id") or "checkpoint",
            "result_hash": checkpoint.get("last_result_hash") or ("0" * 64),
        }

    emitted = stored = duplicates = segments = 0
    safe_cursor = cursor
    batch: list[dict[str, Any]] = []

    def flush_batch() -> None:
        nonlocal previous, emitted, stored, duplicates, segments, safe_cursor, batch
        if previous is None or not batch:
            return
        payload = _trajectory_request(world_id=world_id, previous=previous, moves=batch)
        response = send(payload)
        _validate_ack(response, payload)
        emitted += 1
        stored += int(response["stored"])
        duplicates += int(response["duplicate"])
        segments += len(batch)
        previous = batch[-1]
        safe_cursor = int(previous["_row_end"])
        _write_checkpoint(
            checkpoint_path,
            _checkpoint_payload(
                world_id=world_id, delta_path=delta_path,
                cursor=safe_cursor, previous=previous,
            ),
        )
        batch = []

    with delta_path.open("rb") as fh:
        info = os.fstat(fh.fileno())
        if cursor > info.st_size:
            raise SpatialMemorySyncError("delta_ledger_truncated")
        fh.seek(cursor)
        data = fh.read(min(MAX_WINDOW_BYTES, info.st_size - cursor))

    consumed = 0
    for raw_line in data.splitlines(keepends=True):
        if not raw_line.endswith(b"\n"):
            break
        if len(raw_line) > MAX_LINE_BYTES:
            raise SpatialMemorySyncError("delta_line_exceeds_limit")
        row_offset = cursor + consumed
        consumed += len(raw_line)
        row_end = cursor + consumed
        try:
            row = json.loads(raw_line)
        except (ValueError, UnicodeError) as exc:
            raise SpatialMemorySyncError("delta_record_invalid") from exc
        if not isinstance(row, dict):
            raise SpatialMemorySyncError("delta_record_invalid")
        move = _move_from_delta(row)
        if move is None:
            continue
        move["_row_offset"] = row_offset
        move["_row_end"] = row_end

        compare = batch[-1] if batch else previous
        if compare is not None and move["sequence"] <= int(compare.get("sequence") or -1):
            raise SpatialMemorySyncError("delta_sequence_not_monotonic")
        if previous is None:
            previous = move
            safe_cursor = row_end
            continue

        batch.append(move)
        if len(batch) >= moves_per_event:
            flush_batch()
            if emitted >= max_events:
                break

    if batch and emitted < max_events:
        flush_batch()

    if emitted == 0 and previous is not None and safe_cursor != cursor:
        _write_checkpoint(
            checkpoint_path,
            _checkpoint_payload(
                world_id=world_id, delta_path=delta_path,
                cursor=safe_cursor, previous=previous,
            ),
        )

    return {
        "status": "ok",
        "mode": "memoria-structural-spatial-trajectory-v2",
        "world_id": world_id,
        "cursor": safe_cursor,
        "emitted": emitted,
        "segments": segments,
        "stored": stored,
        "duplicates": duplicates,
        "moves_per_event": moves_per_event,
        "world_mutated": False,
        "selection_authority": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-events", type=int, default=MAX_EVENTS_PER_RUN)
    args = parser.parse_args()
    try:
        result = sync_once(max_events=args.max_events)
    except SpatialMemorySyncError as exc:
        raise SystemExit(f"NOV_SPATIAL_MEMORY_SYNC_BLOCKED {exc}") from exc
    print("NOV_SPATIAL_MEMORY_SYNC_OK " + json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
