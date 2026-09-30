"""Rebuildable SQLite sidecar index for PlanLedger JSONL.

The JSONL remains authoritative. This index stores only lookup metadata and can
always be discarded/rebuilt. It avoids reparsing hundreds of MB of terminal plan
payloads after every autonomous-world restart.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator

SCHEMA = "live-infinita-plan-ledger-index/v1"
TERMINAL = frozenset({"completed", "failed", "cancelled"})


class PlanLedgerSidecarError(RuntimeError):
    pass


class PlanLedgerSidecar:
    def __init__(self, source: Path, *, commit_every: int = 32) -> None:
        self.source = Path(source)
        self.path = self.source.with_name(self.source.name + ".index.sqlite3")
        self.commit_every = max(1, int(commit_every))
        self._db: sqlite3.Connection | None = None
        self._pending = 0

    @staticmethod
    def _eligible_need_candidate(row: dict[str, Any]) -> bool:
        intent = row.get("intent")
        return (
            row.get("status") == "completed"
            and isinstance(intent, dict)
            and bool(intent.get("need"))
            and intent.get("need_outcome_eligible") is not False
        )

    def _connect(self) -> sqlite3.Connection:
        if self._db is not None:
            return self._db
        db = sqlite3.connect(self.path, timeout=30.0)
        db.execute("PRAGMA journal_mode=WAL")
        # The sidecar is a cache. NORMAL keeps SQLite transactional while avoiding
        # FULL durability cost on every derived-index update.
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS plans ("
            "plan_id TEXT PRIMARY KEY,"
            "first_seq INTEGER NOT NULL,"
            "offset INTEGER NOT NULL,"
            "idempotency_key TEXT,"
            "status TEXT NOT NULL,"
            "actor_entity_id TEXT,"
            "need_candidate INTEGER NOT NULL DEFAULT 0)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_plans_idempotency "
            "ON plans(idempotency_key, first_seq)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_plans_status "
            "ON plans(status, first_seq)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_plans_need "
            "ON plans(need_candidate, first_seq)"
        )
        self._db = db
        return db

    def close(self, *, commit: bool = True) -> None:
        db = self._db
        if db is None:
            return
        try:
            if commit:
                db.commit()
            else:
                db.rollback()
        finally:
            db.close()
            self._db = None
            self._pending = 0

    def __del__(self) -> None:
        try:
            # Uncommitted sidecar cache rows may be replayed from the JSONL tail.
            self.close(commit=False)
        except Exception:
            pass

    @staticmethod
    def _first_record_digest(path: Path) -> str:
        with path.open("rb") as fh:
            for raw in fh:
                if raw.strip():
                    return sha256(raw).hexdigest()
        return ""

    def _meta(self, key: str) -> str | None:
        db = self._connect()
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None

    def _set_meta(self, key: str, value: Any) -> None:
        self._connect().execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    @staticmethod
    def _source_signature(path: Path) -> tuple[int, int, int, int]:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    @staticmethod
    def _iter_from(path: Path, start: int = 0) -> Iterator[tuple[int, dict[str, Any], int]]:
        with path.open("rb") as fh:
            fh.seek(int(start))
            while True:
                offset = fh.tell()
                raw = fh.readline()
                if not raw:
                    break
                end = fh.tell()
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise PlanLedgerSidecarError(
                        f"invalid plan JSONL at byte {offset}"
                    ) from exc
                if not isinstance(row, dict):
                    continue
                plan_id = str(row.get("plan_id") or "").strip()
                if not plan_id:
                    continue
                yield offset, row, end

    def _apply_row(
        self,
        *,
        offset: int,
        row: dict[str, Any],
        seq_if_new: int,
    ) -> int:
        db = self._connect()
        plan_id = str(row.get("plan_id") or "").strip()
        existing = db.execute(
            "SELECT first_seq FROM plans WHERE plan_id=?",
            (plan_id,),
        ).fetchone()
        first_seq = int(existing[0]) if existing else int(seq_if_new)
        db.execute(
            "INSERT INTO plans("
            "plan_id,first_seq,offset,idempotency_key,status,actor_entity_id,need_candidate"
            ") VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(plan_id) DO UPDATE SET "
            "offset=excluded.offset,"
            "idempotency_key=excluded.idempotency_key,"
            "status=excluded.status,"
            "actor_entity_id=excluded.actor_entity_id,"
            "need_candidate=excluded.need_candidate",
            (
                plan_id,
                first_seq,
                int(offset),
                str(row.get("idempotency_key") or "") or None,
                str(row.get("status") or ""),
                str(row.get("actor_entity_id") or "") or None,
                1 if self._eligible_need_candidate(row) else 0,
            ),
        )
        return first_seq

    def _reset(self) -> None:
        self.close(commit=False)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
        self._connect()

    def rebuild(self) -> dict[str, int]:
        if not self.source.is_file() or self.source.is_symlink():
            raise PlanLedgerSidecarError("plan ledger source unavailable")
        self._reset()
        db = self._connect()
        before = self._source_signature(self.source)
        next_seq = 0
        rows = 0
        indexed_size = 0
        db.execute("BEGIN")
        for offset, row, end in self._iter_from(self.source, 0):
            existing = db.execute(
                "SELECT first_seq FROM plans WHERE plan_id=?",
                (str(row.get("plan_id") or ""),),
            ).fetchone()
            if existing is None:
                seq = next_seq
                next_seq += 1
            else:
                seq = int(existing[0])
            self._apply_row(offset=offset, row=row, seq_if_new=seq)
            rows += 1
            indexed_size = end
        after = self._source_signature(self.source)
        if before != after:
            db.rollback()
            raise PlanLedgerSidecarError("plan ledger changed while rebuilding sidecar")
        self._set_meta("schema", SCHEMA)
        self._set_meta("source_dev", after[0])
        self._set_meta("source_ino", after[1])
        self._set_meta("indexed_size", after[2])
        self._set_meta("source_mtime_ns", after[3])
        self._set_meta("first_record_sha256", self._first_record_digest(self.source))
        self._set_meta("next_seq", next_seq)
        db.commit()
        self._pending = 0
        return {"rows": rows, "plans": next_seq, "indexed_size": after[2]}

    def _metadata_valid_for(self, sig: tuple[int, int, int, int]) -> bool:
        try:
            return (
                self._meta("schema") == SCHEMA
                and int(self._meta("source_dev") or -1) == sig[0]
                and int(self._meta("source_ino") or -1) == sig[1]
                and 0 <= int(self._meta("indexed_size") or -1) <= sig[2]
                and self._meta("first_record_sha256")
                    == self._first_record_digest(self.source)
            )
        except (ValueError, TypeError, sqlite3.DatabaseError):
            return False

    def ensure(self) -> dict[str, int]:
        if not self.source.is_file() or self.source.is_symlink():
            raise PlanLedgerSidecarError("plan ledger source unavailable")
        try:
            sig = self._source_signature(self.source)
            if not self.path.exists():
                return self.rebuild()
            self._connect()
            if not self._metadata_valid_for(sig):
                return self.rebuild()

            indexed_size = int(self._meta("indexed_size") or 0)
            indexed_mtime = int(self._meta("source_mtime_ns") or 0)
            if indexed_size == sig[2]:
                if indexed_mtime != sig[3]:
                    return self.rebuild()
                return {
                    "rows": 0,
                    "plans": self.count(),
                    "indexed_size": indexed_size,
                }

            db = self._connect()
            next_seq = int(self._meta("next_seq") or 0)
            before = self._source_signature(self.source)
            rows = 0
            end_offset = indexed_size
            db.execute("BEGIN")
            for offset, row, end in self._iter_from(self.source, indexed_size):
                existing = db.execute(
                    "SELECT first_seq FROM plans WHERE plan_id=?",
                    (str(row.get("plan_id") or ""),),
                ).fetchone()
                if existing is None:
                    seq = next_seq
                    next_seq += 1
                else:
                    seq = int(existing[0])
                self._apply_row(offset=offset, row=row, seq_if_new=seq)
                rows += 1
                end_offset = end
            after = self._source_signature(self.source)
            if before != after or end_offset != after[2]:
                db.rollback()
                raise PlanLedgerSidecarError(
                    "plan ledger changed while applying sidecar tail"
                )
            self._set_meta("indexed_size", after[2])
            self._set_meta("source_mtime_ns", after[3])
            self._set_meta("first_record_sha256", self._first_record_digest(self.source))
            self._set_meta("next_seq", next_seq)
            db.commit()
            self._pending = 0
            return {"rows": rows, "plans": self.count(), "indexed_size": after[2]}
        except sqlite3.DatabaseError:
            return self.rebuild()

    def count(self) -> int:
        row = self._connect().execute("SELECT COUNT(*) FROM plans").fetchone()
        return int(row[0]) if row else 0

    def materialized_rows(self) -> list[tuple[str, int, int, str, str, int]]:
        return [
            (
                str(plan_id),
                int(first_seq),
                int(offset),
                str(idempotency_key or ""),
                str(status or ""),
                int(need_candidate),
            )
            for plan_id, first_seq, offset, idempotency_key, status, need_candidate
            in self._connect().execute(
                "SELECT plan_id,first_seq,offset,idempotency_key,status,need_candidate "
                "FROM plans ORDER BY first_seq"
            )
        ]

    def note_append(
        self,
        *,
        offset: int,
        row: dict[str, Any],
        source_signature: tuple[int, int, int, int],
    ) -> None:
        # If no valid sidecar exists, leave recovery to ensure()/rebuild().
        if not self.path.exists():
            return
        try:
            self._connect()
            current_dev = int(self._meta("source_dev") or -1)
            current_ino = int(self._meta("source_ino") or -1)
            if (current_dev, current_ino) != source_signature[:2]:
                return
            next_seq = int(self._meta("next_seq") or 0)
            existing = self._connect().execute(
                "SELECT first_seq FROM plans WHERE plan_id=?",
                (str(row.get("plan_id") or ""),),
            ).fetchone()
            if existing is None:
                seq = next_seq
                next_seq += 1
            else:
                seq = int(existing[0])
            if self._pending == 0:
                self._connect().execute("BEGIN")
            self._apply_row(offset=offset, row=row, seq_if_new=seq)
            self._set_meta("indexed_size", source_signature[2])
            self._set_meta("source_mtime_ns", source_signature[3])
            self._set_meta("next_seq", next_seq)
            self._pending += 1
            if self._pending >= self.commit_every:
                self._connect().commit()
                self._pending = 0
        except sqlite3.DatabaseError:
            # Sidecar failure must never make the authoritative JSONL append fail.
            self.close(commit=False)

    def flush(self) -> None:
        if self._db is not None and self._pending:
            self._db.commit()
            self._pending = 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    index = PlanLedgerSidecar(args.source)
    try:
        result = index.rebuild() if args.rebuild else index.ensure()
        index.flush()
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "source": str(args.source),
                    "index": str(index.path),
                    **result,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    finally:
        index.close(commit=True)


if __name__ == "__main__":
    main()
