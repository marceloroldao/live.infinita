"""Compact append-only runtime ledgers into small hot-state ledgers.

The original file is atomically renamed to an immutable .archive-* file. The
active path is replaced by one latest row per logical object. No history bytes
are deleted. This tool must run while the autonomous single writer is stopped.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Iterator

MANIFEST_SCHEMA = "live-infinita-hot-ledger-compaction/v1"


class CompactionError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _iter_strict_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any], bytes]]:
    with path.open("rb") as fh:
        line_number = 0
        while True:
            raw = fh.readline()
            if not raw:
                break
            line_number += 1
            if not raw.strip():
                continue
            try:
                value = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CompactionError(
                    f"{path.name}: invalid JSONL at line {line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise CompactionError(
                    f"{path.name}: non-object JSONL at line {line_number}"
                )
            yield line_number, value, raw


def _archive_name(path: Path, digest: str) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return path.with_name(f"{path.name}.archive-{stamp}-{digest[:12]}.jsonl")


def _atomic_swap(
    *,
    source: Path,
    compact: Path,
    archive: Path,
    manifest: dict[str, Any],
) -> None:
    if archive.exists():
        raise CompactionError(f"archive already exists: {archive}")
    stat = source.stat()
    os.chmod(compact, stat.st_mode & 0o777)
    try:
        os.chown(compact, stat.st_uid, stat.st_gid)
    except PermissionError:
        # Unit tests/non-root use may not be able to chown; ownership already
        # matches when the caller owns both files.
        pass

    manifest_path = source.with_name(source.name + ".compaction.json")
    manifest_tmp = manifest_path.with_name(manifest_path.name + f".{os.getpid()}.tmp")
    manifest_tmp.write_bytes(_canonical(manifest))
    with manifest_tmp.open("rb") as fh:
        os.fsync(fh.fileno())

    os.replace(source, archive)
    try:
        os.replace(compact, source)
        os.replace(manifest_tmp, manifest_path)
        folder_fd = os.open(source.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(folder_fd)
        finally:
            os.close(folder_fd)
    except BaseException:
        if not source.exists() and archive.exists():
            os.replace(archive, source)
        raise


def compact_conditional(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CompactionError("conditional ledger unavailable")
    manifest_path = path.with_name(path.name + ".compaction.json")
    if manifest_path.exists():
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("schema") == MANIFEST_SCHEMA:
            return {**value, "already_compacted": True}
        raise CompactionError("conditional compaction manifest invalid")

    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    digest = sha256()
    rows = 0
    for _, row, raw in _iter_strict_jsonl(path):
        digest.update(raw)
        rows += 1
        event_id = str(row.get("conditional_event_id") or "").strip()
        if not event_id:
            raise CompactionError("conditional row without conditional_event_id")
        if event_id not in latest:
            order.append(event_id)
        latest[event_id] = row

    if not latest:
        raise CompactionError("conditional ledger has no state rows")

    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".compact-", dir=path.parent
    )
    compact = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            for event_id in order:
                out.write(_canonical(latest[event_id]))
            out.flush()
            os.fsync(out.fileno())
        compact_bytes = compact.stat().st_size
        original_bytes = path.stat().st_size
        source_digest = digest.hexdigest()
        archive = _archive_name(path, source_digest)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "kind": "conditional",
            "source": path.name,
            "archive": archive.name,
            "source_sha256": source_digest,
            "original_rows": rows,
            "latest_rows": len(latest),
            "original_bytes": original_bytes,
            "compact_bytes": compact_bytes,
            "history_deleted": False,
        }
        _atomic_swap(
            source=path,
            compact=compact,
            archive=archive,
            manifest=manifest,
        )
        return manifest
    finally:
        if compact.exists():
            compact.unlink()


def compact_plans(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CompactionError("plan ledger unavailable")
    manifest_path = path.with_name(path.name + ".compaction.json")
    if manifest_path.exists():
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("schema") == MANIFEST_SCHEMA:
            return {**value, "already_compacted": True}
        raise CompactionError("plan compaction manifest invalid")

    db_fd, db_name = tempfile.mkstemp(
        prefix=path.name + ".index-", suffix=".sqlite3", dir=path.parent
    )
    os.close(db_fd)
    db_path = Path(db_name)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".compact-", dir=path.parent
    )
    os.close(fd)
    compact = Path(temp_name)
    digest = sha256()
    rows = 0
    try:
        db = sqlite3.connect(db_path)
        try:
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute(
                "CREATE TABLE latest ("
                "plan_id TEXT PRIMARY KEY, first_seq INTEGER NOT NULL, payload BLOB NOT NULL)"
            )
            db.execute("BEGIN")
            for seq, (_, row, raw) in enumerate(_iter_strict_jsonl(path)):
                digest.update(raw)
                rows += 1
                plan_id = str(row.get("plan_id") or "").strip()
                if not plan_id:
                    raise CompactionError("plan row without plan_id")
                payload = _canonical(row)
                db.execute(
                    "INSERT INTO latest(plan_id,first_seq,payload) VALUES(?,?,?) "
                    "ON CONFLICT(plan_id) DO UPDATE SET payload=excluded.payload",
                    (plan_id, seq, payload),
                )
                if rows % 10000 == 0:
                    db.commit()
                    db.execute("BEGIN")
            db.commit()
            unique_rows = int(db.execute("SELECT COUNT(*) FROM latest").fetchone()[0])
            if unique_rows <= 0:
                raise CompactionError("plan ledger has no state rows")

            with compact.open("wb") as out:
                cursor = db.execute(
                    "SELECT payload FROM latest ORDER BY first_seq, plan_id"
                )
                for (payload,) in cursor:
                    out.write(bytes(payload))
                out.flush()
                os.fsync(out.fileno())
        finally:
            db.close()

        compact_bytes = compact.stat().st_size
        original_bytes = path.stat().st_size
        source_digest = digest.hexdigest()
        archive = _archive_name(path, source_digest)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "kind": "plans",
            "source": path.name,
            "archive": archive.name,
            "source_sha256": source_digest,
            "original_rows": rows,
            "latest_rows": unique_rows,
            "original_bytes": original_bytes,
            "compact_bytes": compact_bytes,
            "history_deleted": False,
        }
        _atomic_swap(
            source=path,
            compact=compact,
            archive=archive,
            manifest=manifest,
        )
        return manifest
    finally:
        if db_path.exists():
            db_path.unlink()
        if compact.exists():
            compact.unlink()


def compact_proposals(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CompactionError("proposal ledger unavailable")
    manifest_path = path.with_name(path.name + ".compaction.json")
    if manifest_path.exists():
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("schema") == MANIFEST_SCHEMA:
            return {**value, "already_compacted": True}
        raise CompactionError("proposal compaction manifest invalid")

    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    digest = sha256()
    rows = 0
    for _, row, raw in _iter_strict_jsonl(path):
        digest.update(raw)
        rows += 1
        proposal_id = str(row.get("proposal_id") or "").strip()
        if not proposal_id:
            raise CompactionError("proposal row without proposal_id")
        if proposal_id not in latest:
            order.append(proposal_id)
        latest[proposal_id] = row

    if not latest:
        raise CompactionError("proposal ledger has no state rows")

    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".compact-", dir=path.parent
    )
    compact = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            for proposal_id in order:
                out.write(_canonical(latest[proposal_id]))
            out.flush()
            os.fsync(out.fileno())
        compact_bytes = compact.stat().st_size
        original_bytes = path.stat().st_size
        source_digest = digest.hexdigest()
        archive = _archive_name(path, source_digest)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "kind": "proposals",
            "source": path.name,
            "archive": archive.name,
            "source_sha256": source_digest,
            "original_rows": rows,
            "latest_rows": len(latest),
            "original_bytes": original_bytes,
            "compact_bytes": compact_bytes,
            "history_deleted": False,
        }
        _atomic_swap(
            source=path,
            compact=compact,
            archive=archive,
            manifest=manifest,
        )
        return manifest
    finally:
        if compact.exists():
            compact.unlink()


def compact_need_scheduler(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise CompactionError("npc need scheduler ledger unavailable")
    manifest_path = path.with_name(path.name + ".compaction.json")
    if manifest_path.exists():
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("schema") == MANIFEST_SCHEMA:
            return {**value, "already_compacted": True}
        raise CompactionError("npc need compaction manifest invalid")

    latest_audit: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    latest_scheduled_original: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    latest_scheduled_actual: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    digest = sha256()
    rows = 0
    for seq, (_, row, raw) in enumerate(_iter_strict_jsonl(path)):
        digest.update(raw)
        rows += 1
        npc_id = str(row.get("npc_id") or "").strip()
        original_need = str(
            row.get("original_need") or row.get("need") or ""
        ).strip()
        if not npc_id or not original_need:
            raise CompactionError("npc need row without audit key")
        audit_key = (npc_id, original_need)
        latest_audit[audit_key] = (seq, row)
        if row.get("status") == "scheduled":
            latest_scheduled_original[audit_key] = (seq, row)
            actual_need = str(row.get("need") or "").strip()
            if actual_need:
                latest_scheduled_actual[(npc_id, actual_need)] = (seq, row)

    selected_by_seq: dict[int, dict[str, Any]] = {}
    for seq, row in latest_audit.values():
        selected_by_seq[seq] = row
    for seq, row in latest_scheduled_original.values():
        selected_by_seq[seq] = row
    for seq, row in latest_scheduled_actual.values():
        selected_by_seq[seq] = row
    if not selected_by_seq:
        raise CompactionError("npc need ledger has no hot state rows")

    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".compact-", dir=path.parent
    )
    compact = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            for seq in sorted(selected_by_seq):
                out.write(_canonical(selected_by_seq[seq]))
            out.flush()
            os.fsync(out.fileno())
        compact_bytes = compact.stat().st_size
        original_bytes = path.stat().st_size
        source_digest = digest.hexdigest()
        archive = _archive_name(path, source_digest)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "kind": "npc_need_scheduler",
            "source": path.name,
            "archive": archive.name,
            "source_sha256": source_digest,
            "original_rows": rows,
            "latest_rows": len(selected_by_seq),
            "latest_audit_keys": len(latest_audit),
            "latest_scheduled_original_keys": len(latest_scheduled_original),
            "latest_scheduled_actual_keys": len(latest_scheduled_actual),
            "original_bytes": original_bytes,
            "compact_bytes": compact_bytes,
            "history_deleted": False,
        }
        _atomic_swap(
            source=path,
            compact=compact,
            archive=archive,
            manifest=manifest,
        )
        return manifest
    finally:
        if compact.exists():
            compact.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conditional", type=Path)
    parser.add_argument("--plans", type=Path)
    parser.add_argument("--proposals", type=Path)
    parser.add_argument("--needs", type=Path)
    args = parser.parse_args()
    if (
        args.conditional is None
        and args.plans is None
        and args.proposals is None
        and args.needs is None
    ):
        raise SystemExit("at least one ledger path is required")
    results: list[dict[str, Any]] = []
    if args.conditional is not None:
        results.append(compact_conditional(args.conditional))
    if args.plans is not None:
        results.append(compact_plans(args.plans))
    if args.proposals is not None:
        results.append(compact_proposals(args.proposals))
    if args.needs is not None:
        results.append(compact_need_scheduler(args.needs))
    print(
        "HOT_LEDGER_COMPACTION_OK "
        + json.dumps(results, sort_keys=True, separators=(",", ":")),
        flush=True,
    )


if __name__ == "__main__":
    main()
