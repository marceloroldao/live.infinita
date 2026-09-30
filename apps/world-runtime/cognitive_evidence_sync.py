from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from packages.observability.cognitive_evidence import (
    CognitiveEvidenceError,
    to_structural_text_request,
    validate_evidence,
)

CHECKPOINT_SCHEMA = "live-infinita-cognitive-evidence-sync-checkpoint/v1"
LOCAL_ENDPOINT = "http://127.0.0.1:8788/api/v1/structural/text/observe"
ROOT = Path(os.environ.get("LIVE_INFINITA_DATA_DIR", "/var/lib/live-infinita"))
LOCAL_ROOT = Path("/var/lib/live-infinita/memoria-local")
MAX_LINE_BYTES = 131_072


class CognitiveEvidenceSyncError(RuntimeError):
    pass


def _identity(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError as exc:
        raise CognitiveEvidenceSyncError("evidence_ledger_unavailable") from exc
    return f"{stat.st_dev}:{stat.st_ino}"


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink():
        raise CognitiveEvidenceSyncError("checkpoint_symlink")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CognitiveEvidenceSyncError("checkpoint_unreadable") from exc
    if len(raw) > 32_768:
        raise CognitiveEvidenceSyncError("checkpoint_oversized")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CognitiveEvidenceSyncError("checkpoint_invalid") from exc
    if not isinstance(value, dict) or value.get("schema") != CHECKPOINT_SCHEMA:
        raise CognitiveEvidenceSyncError("checkpoint_schema_mismatch")
    cursor = value.get("cursor")
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise CognitiveEvidenceSyncError("checkpoint_cursor_invalid")
    return value


def _write_checkpoint(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        written = os.write(fd, payload)
        if written != len(payload):
            raise CognitiveEvidenceSyncError("checkpoint_short_write")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _read_next(
    ledger: Path,
    *,
    cursor: int,
) -> tuple[dict[str, Any] | None, int, str, int]:
    identity = _identity(ledger)
    try:
        size = ledger.stat().st_size
    except OSError as exc:
        raise CognitiveEvidenceSyncError("evidence_ledger_unavailable") from exc
    if cursor > size:
        raise CognitiveEvidenceSyncError("ledger_truncated")
    try:
        with ledger.open("rb") as fh:
            if cursor:
                fh.seek(cursor - 1)
                if fh.read(1) != b"\n":
                    raise CognitiveEvidenceSyncError("cursor_not_line_boundary")
            fh.seek(cursor)
            raw = fh.readline(MAX_LINE_BYTES + 1)
    except OSError as exc:
        raise CognitiveEvidenceSyncError("evidence_ledger_unavailable") from exc

    if not raw:
        return None, cursor, identity, size
    if len(raw) > MAX_LINE_BYTES:
        raise CognitiveEvidenceSyncError("evidence_line_exceeds_limit")
    if not raw.endswith(b"\n"):
        return None, cursor, identity, size
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CognitiveEvidenceSyncError("malformed_evidence_record") from exc
    try:
        validate_evidence(record)
    except CognitiveEvidenceError as exc:
        raise CognitiveEvidenceSyncError("invalid_evidence_record") from exc
    return record, cursor + len(raw), identity, size


def _post_local(request_payload: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("MEMORIA_API_KEY", "")
    if not api_key or len(api_key) < 32:
        raise CognitiveEvidenceSyncError("local_api_key_unconfigured")
    body = json.dumps(
        request_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    request = Request(
        LOCAL_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Memoria-Key": api_key,
        },
    )
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=20) as response:
            raw = response.read(16_385)
            if response.status != 201 or len(raw) > 16_384:
                raise CognitiveEvidenceSyncError("invalid_local_server_response")
    except HTTPError as exc:
        raise CognitiveEvidenceSyncError(f"local_server_http_{exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CognitiveEvidenceSyncError("local_server_unavailable") from exc
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise CognitiveEvidenceSyncError("invalid_local_server_response") from exc
    if not isinstance(value, dict):
        raise CognitiveEvidenceSyncError("invalid_local_server_response")
    return value


def _validate_receipt(receipt: dict[str, Any]) -> None:
    stored = receipt.get("stored")
    duplicate = receipt.get("duplicate")
    if not isinstance(stored, bool) or not isinstance(duplicate, bool):
        raise CognitiveEvidenceSyncError("invalid_structural_receipt")
    if stored == duplicate:
        raise CognitiveEvidenceSyncError("invalid_structural_receipt")
    observation_id = str(receipt.get("observation_id") or "")
    if not observation_id.startswith("structural-event:"):
        raise CognitiveEvidenceSyncError("invalid_structural_receipt")
    if receipt.get("semantic_projection") is not False:
        raise CognitiveEvidenceSyncError("semantic_projection_must_remain_false")


def sync_once(
    ledger: Path,
    checkpoint_path: Path,
    *,
    send: Callable[[dict[str, Any]], dict[str, Any]] = _post_local,
    max_records: int = 16,
) -> dict[str, Any]:
    if isinstance(max_records, bool) or not isinstance(max_records, int):
        raise CognitiveEvidenceSyncError("invalid_max_records")
    if not 1 <= max_records <= 128:
        raise CognitiveEvidenceSyncError("invalid_max_records")

    checkpoint = _read_checkpoint(checkpoint_path)
    cursor = int((checkpoint or {}).get("cursor", 0))
    expected_identity = (checkpoint or {}).get("ledger_identity")
    if expected_identity is not None and expected_identity != _identity(ledger):
        raise CognitiveEvidenceSyncError("ledger_inode_changed")

    acked = 0
    stored = 0
    duplicates = 0
    last = checkpoint
    for _ in range(max_records):
        record, candidate, ledger_identity, ledger_size = _read_next(
            ledger,
            cursor=cursor,
        )
        if record is None:
            break
        if expected_identity is not None and ledger_identity != expected_identity:
            raise CognitiveEvidenceSyncError("ledger_inode_changed")

        request_payload = to_structural_text_request(record)
        receipt = send(request_payload)
        _validate_receipt(receipt)

        acked += 1
        stored += int(receipt["stored"])
        duplicates += int(receipt["duplicate"])
        last = {
            "schema": CHECKPOINT_SCHEMA,
            "ledger_identity": ledger_identity,
            "cursor": candidate,
            "ledger_size_at_ack": ledger_size,
            "last_record_key": record["record_key"],
            "last_content_sha256": record["content_sha256"],
            "last_observation_id": receipt["observation_id"],
            "acked_records": int((checkpoint or {}).get("acked_records", 0)) + acked,
            "stored_records": int((checkpoint or {}).get("stored_records", 0)) + stored,
            "duplicate_records": int((checkpoint or {}).get("duplicate_records", 0)) + duplicates,
            "updated_at_unix": time.time(),
        }
        _write_checkpoint(checkpoint_path, last)
        cursor = candidate
        expected_identity = ledger_identity

    return {
        "status": "ok",
        "mode": "local-memoria-structural-text",
        "acked": acked,
        "stored": stored,
        "duplicates": duplicates,
        "cursor": cursor,
        "ledger_identity": expected_identity,
        "world_mutated": False,
        "selection_authority": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Live Infinita social cognitive evidence into local Memoria.ia"
    )
    parser.add_argument("--max-records", type=int, default=16)
    args = parser.parse_args()
    ledger = ROOT / "cognitive-evidence.jsonl"
    checkpoint = LOCAL_ROOT / "cognitive-evidence-sync.checkpoint.json"
    try:
        result = sync_once(
            ledger,
            checkpoint,
            max_records=args.max_records,
        )
    except (CognitiveEvidenceSyncError, CognitiveEvidenceError, OSError) as exc:
        raise SystemExit(
            f"COGNITIVE_EVIDENCE_SYNC_BLOCKED {type(exc).__name__}: {exc}"
        ) from exc
    print(
        "COGNITIVE_EVIDENCE_SYNC_OK "
        + json.dumps(result, sort_keys=True, separators=(",", ":")),
        flush=True,
    )


if __name__ == "__main__":
    main()
