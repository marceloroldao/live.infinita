"""Low-priority, local-only bridge from the authoritative Nov ledger to Memoria.ia V2.

The world Single Writer is never imported or invoked. Records are read from the
existing ledger and stored in a *separate* local Memoria.ia instance. No central
network route, chat/LLM coercion, or world mutation is permitted.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packages.observability.nov_episode_sync import (
    EpisodeSyncContractError, preview_episode_batch,
)

ROOT = Path("/var/lib/live-infinita/autonomous-world")
LOCAL_ROOT = Path("/var/lib/live-infinita/memoria-local")
LOCAL_ENDPOINT = "http://127.0.0.1:8788/api/v1/external/episodes"
CHECKPOINT_SCHEMA = "live-infinita-nov-local-memory-checkpoint/v1"
OBSERVATION_SCHEMA = "live-infinita-npc-episode-observation/v1"
MAX_CHECKPOINT_BYTES = 8192
MAX_LINE_BYTES = 262_144
MAX_PREFIX_BYTES = 4096
HEX = re.compile(r"^[0-9a-f]{64}$")


class LocalMemorySyncError(RuntimeError):
    pass


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _line_digest_at_cursor(path: Path, cursor: int) -> str | None:
    if cursor == 0:
        return None
    with path.open("rb") as fh:
        if fh.seek(0, os.SEEK_END) < cursor:
            raise LocalMemorySyncError("ledger_truncated")
        fh.seek(cursor - 1)
        if fh.read(1) != b"\n":
            raise LocalMemorySyncError("cursor_not_complete_line")
        start = max(0, cursor - MAX_LINE_BYTES)
        fh.seek(start)
        data = fh.read(cursor - start)
    # Require a full previous line. At offset=0 no preceding delimiter exists.
    previous = data[:-1].rfind(b"\n")
    if start and previous < 0:
        raise LocalMemorySyncError("checkpoint_line_exceeds_window")
    line = data[previous + 1:]
    if not line.endswith(b"\n"):
        raise LocalMemorySyncError("checkpoint_line_not_complete")
    return _digest(line)


def _prefix_digest(path: Path, cursor: int) -> str:
    with path.open("rb") as fh:
        data = fh.read(min(cursor, MAX_PREFIX_BYTES))
    if len(data) != min(cursor, MAX_PREFIX_BYTES):
        raise LocalMemorySyncError("ledger_truncated")
    return _digest(data)


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise LocalMemorySyncError("checkpoint_symlink")
    try:
        if path.stat().st_size > MAX_CHECKPOINT_BYTES:
            raise LocalMemorySyncError("checkpoint_oversized")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeError) as exc:
        raise LocalMemorySyncError("checkpoint_unreadable") from exc
    if not isinstance(value, dict) or value.get("schema") != CHECKPOINT_SCHEMA:
        raise LocalMemorySyncError("checkpoint_schema_mismatch")
    if isinstance(value.get("cursor"), bool) or not isinstance(value.get("cursor"), int) or value["cursor"] < 0:
        raise LocalMemorySyncError("checkpoint_cursor_invalid")
    for field in ("world_id", "ledger_identity"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise LocalMemorySyncError("checkpoint_identity_invalid")
    for field in ("prefix_sha256",):
        if not isinstance(value.get(field), str) or not HEX.fullmatch(value[field]):
            raise LocalMemorySyncError("checkpoint_integrity_invalid")
    if value.get("cursor") == 0:
        if value.get("last_line_sha256") is not None:
            raise LocalMemorySyncError("checkpoint_line_invalid")
    elif not isinstance(value.get("last_line_sha256"), str) or not HEX.fullmatch(value["last_line_sha256"]):
        raise LocalMemorySyncError("checkpoint_line_invalid")
    return value


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise LocalMemorySyncError("checkpoint_symlink")
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if len(encoded) > MAX_CHECKPOINT_BYTES:
        raise LocalMemorySyncError("checkpoint_oversized")
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
        folder = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if temp.exists():
            temp.unlink()


def _checkpoint_validate(checkpoint: dict[str, Any] | None, *, ledger: Path, batch: dict[str, Any]) -> None:
    if checkpoint is None:
        return
    if checkpoint["world_id"] != batch["world_id"]:
        raise LocalMemorySyncError("world_identity_changed")
    if checkpoint["ledger_identity"] != batch["ledger_identity"]:
        raise LocalMemorySyncError("ledger_inode_changed")
    cursor = checkpoint["cursor"]
    if batch["ledger_size_at_read"] < cursor:
        raise LocalMemorySyncError("ledger_truncated")
    if checkpoint["prefix_sha256"] != _prefix_digest(ledger, cursor):
        raise LocalMemorySyncError("ledger_prefix_rewritten")
    if checkpoint["last_line_sha256"] != _line_digest_at_cursor(ledger, cursor):
        raise LocalMemorySyncError("last_acked_line_rewritten")


def _validate_receipt(receipt: dict[str, Any], observation: dict[str, Any]) -> None:
    if not isinstance(receipt, dict) or receipt.get("ack") is not True:
        raise LocalMemorySyncError("missing_durable_ack")
    if receipt.get("schema") != OBSERVATION_SCHEMA:
        raise LocalMemorySyncError("receipt_schema_mismatch")
    if receipt.get("record_key") != observation["record_key"] or receipt.get("content_sha256") != observation["content_sha256"]:
        raise LocalMemorySyncError("receipt_identity_mismatch")
    source = observation["source"]
    if receipt.get("episode_id") != source["episode_id"] or receipt.get("world_id") != source["world_id"]:
        raise LocalMemorySyncError("receipt_source_mismatch")
    if receipt.get("world_mutated") is not False or receipt.get("selection_authority") is not False:
        raise LocalMemorySyncError("receipt_authority_mismatch")
    if not isinstance(receipt.get("stored"), bool):
        raise LocalMemorySyncError("receipt_storage_status_missing")
    persisted = receipt.get("persistence")
    if not isinstance(persisted, dict) or persisted.get("backend") not in {"sqlite", "bdr"}:
        raise LocalMemorySyncError("receipt_persistence_missing")
    if not isinstance(persisted.get("state_id"), str) or not persisted["state_id"]:
        raise LocalMemorySyncError("receipt_state_id_missing")
    if not isinstance(persisted.get("sha256"), str) or not HEX.fullmatch(persisted["sha256"]):
        raise LocalMemorySyncError("receipt_digest_invalid")


def _post_local(observation: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("MEMORIA_API_KEY", "")
    if not api_key or len(api_key) < 32:
        raise LocalMemorySyncError("local_api_key_unconfigured")
    body = json.dumps(observation, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(body) > MAX_LINE_BYTES:
        raise LocalMemorySyncError("observation_exceeds_limit")
    req = Request(
        LOCAL_ENDPOINT, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "X-Memoria-Key": api_key},
    )
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read(8193)
            if response.status != 201 or len(raw) > 8192:
                raise LocalMemorySyncError("invalid_local_server_response")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise LocalMemorySyncError("invalid_local_server_response")
        return value
    except HTTPError as exc:
        raise LocalMemorySyncError(f"local_server_http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise LocalMemorySyncError("local_server_unavailable_or_invalid") from exc


def sync_once(
    ledger: Path, world: Path, checkpoint_path: Path, *,
    send: Callable[[dict[str, Any]], dict[str, Any]] = _post_local,
    max_episodes: int = 2,
) -> dict[str, Any]:
    """At-least-once ingestion; commit local cursor only after verified receipt."""
    if isinstance(max_episodes, bool) or not isinstance(max_episodes, int) or not 1 <= max_episodes <= 8:
        raise LocalMemorySyncError("invalid_per_run_limit")
    prior = _read_checkpoint(checkpoint_path)
    cursor = prior["cursor"] if prior is not None else 0
    acked = 0
    skipped = 0
    stored = 0
    last = prior
    for _ in range(max_episodes):
        batch = preview_episode_batch(ledger, world, cursor=cursor, limit=1)
        _checkpoint_validate(prior, ledger=ledger, batch=batch)
        if batch["input_cursor"] != cursor:
            raise LocalMemorySyncError("cursor_mismatch")
        candidate = batch["candidate_next_cursor"]
        if candidate < cursor or candidate > batch["ledger_size_at_read"]:
            raise LocalMemorySyncError("candidate_cursor_invalid")
        if candidate == cursor:
            break
        envelope = batch["episodes"][0] if batch["episodes"] else None
        if envelope is not None:
            receipt = send(envelope)
            _validate_receipt(receipt, envelope)
            acked += 1
            stored += int(receipt["stored"])
        else:
            skipped += 1
        last = {
            "schema": CHECKPOINT_SCHEMA,
            "world_id": batch["world_id"],
            "ledger_identity": batch["ledger_identity"],
            "cursor": candidate,
            "prefix_sha256": _prefix_digest(ledger, candidate),
            "last_line_sha256": _line_digest_at_cursor(ledger, candidate),
            "last_acked_record_key": envelope["record_key"] if envelope else (prior or {}).get("last_acked_record_key"),
            "last_acked_content_sha256": envelope["content_sha256"] if envelope else (prior or {}).get("last_acked_content_sha256"),
            "confirmed_episodes": int((prior or {}).get("confirmed_episodes", 0)) + (1 if envelope is not None else 0),
            "skipped_non_nov_records": int((prior or {}).get("skipped_non_nov_records", 0)) + (1 if envelope is None else 0),
            "updated_at_unix": time.time(),
        }
        _write_checkpoint(checkpoint_path, last)
        prior = last
        cursor = candidate
    return {
        "status": "ok",
        "mode": "local-memoria-v2",
        "acked": acked,
        "stored": stored,
        "skipped": skipped,
        "cursor": cursor,
        "world_id": (last or {}).get("world_id"),
        "central_sync": False,
        "world_mutated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Locally ingest confirmed Nov episodes into Memoria.ia V2")
    parser.add_argument("--max-episodes", type=int, default=2)
    args = parser.parse_args()
    try:
        result = sync_once(
            ROOT / "npc-episodes.jsonl", ROOT / "world.json",
            LOCAL_ROOT / "nov-ingest.checkpoint.json", max_episodes=args.max_episodes,
        )
    except (EpisodeSyncContractError, LocalMemorySyncError, OSError) as exc:
        raise SystemExit(f"LOCAL_MEMORIA_SYNC_BLOCKED {type(exc).__name__}: {exc}") from exc
    print("LOCAL_MEMORIA_SYNC_OK " + json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
