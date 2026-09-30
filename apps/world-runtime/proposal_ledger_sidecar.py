"""Rebuildable SQLite lookup index for ProposalLedger JSONL.

The JSONL is authoritative. SQLite stores only lookup metadata and byte offsets;
proposal payloads never become authoritative sidecar state.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

SCHEMA = "live-infinita-proposal-ledger-index/v1"


class ProposalLedgerSidecarError(RuntimeError):
    pass


class ProposalLedgerSidecar:
    def __init__(self, source: Path, *, commit_every: int = 16) -> None:
        self.source = Path(source)
        self.path = self.source.with_name(self.source.name + ".index.sqlite3")
        self.commit_every = max(1, int(commit_every))
        self._db: sqlite3.Connection | None = None
        self._pending = 0

    def _connect(self) -> sqlite3.Connection:
        if self._db is not None:
            return self._db
        db = sqlite3.connect(self.path, timeout=30.0)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS proposals ("
            "proposal_id TEXT PRIMARY KEY,"
            "first_seq INTEGER NOT NULL,"
            "offset INTEGER NOT NULL,"
            "idempotency_key TEXT,"
            "status TEXT NOT NULL,"
            "origin TEXT,"
            "source_proposal_id TEXT)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_proposals_idempotency "
            "ON proposals(idempotency_key, first_seq)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_proposals_source "
            "ON proposals(origin, source_proposal_id, first_seq)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_proposals_status "
            "ON proposals(status, first_seq)"
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
            self.close(commit=False)
        except Exception:
            pass

    @staticmethod
    def _signature(path: Path) -> tuple[int, int, int, int]:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    @staticmethod
    def _first_record_digest(path: Path) -> str:
        with path.open("rb") as fh:
            for raw in fh:
                if raw.strip():
                    return sha256(raw).hexdigest()
        return ""

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
                    raise ProposalLedgerSidecarError(
                        f"invalid proposal JSONL at byte {offset}"
                    ) from exc
                if not isinstance(row, dict):
                    continue
                proposal_id = str(row.get("proposal_id") or "").strip()
                if proposal_id:
                    yield offset, row, end

    def _meta(self, key: str) -> str | None:
        row = self._connect().execute(
            "SELECT value FROM meta WHERE key=?", (key,)
        ).fetchone()
        return str(row[0]) if row else None

    def _set_meta(self, key: str, value: Any) -> None:
        self._connect().execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def _reset(self) -> None:
        self.close(commit=False)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
        self._connect()

    def _apply(self, offset: int, row: dict[str, Any], seq_if_new: int) -> int:
        db = self._connect()
        proposal_id = str(row.get("proposal_id") or "").strip()
        existing = db.execute(
            "SELECT first_seq FROM proposals WHERE proposal_id=?",
            (proposal_id,),
        ).fetchone()
        first_seq = int(existing[0]) if existing else int(seq_if_new)
        db.execute(
            "INSERT INTO proposals("
            "proposal_id,first_seq,offset,idempotency_key,status,origin,source_proposal_id"
            ") VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(proposal_id) DO UPDATE SET "
            "offset=excluded.offset,"
            "idempotency_key=excluded.idempotency_key,"
            "status=excluded.status,"
            "origin=excluded.origin,"
            "source_proposal_id=excluded.source_proposal_id",
            (
                proposal_id,
                first_seq,
                int(offset),
                str(row.get("idempotency_key") or "") or None,
                str(row.get("status") or ""),
                str(row.get("origin") or "") or None,
                str(row.get("source_proposal_id") or "") or None,
            ),
        )
        return first_seq

    def rebuild(self) -> dict[str, int]:
        if not self.source.is_file() or self.source.is_symlink():
            raise ProposalLedgerSidecarError("proposal source unavailable")
        self._reset()
        db = self._connect()
        before = self._signature(self.source)
        next_seq = 0
        source_rows = 0
        db.execute("BEGIN")
        for offset, row, _end in self._iter_from(self.source):
            proposal_id = str(row.get("proposal_id") or "")
            existing = db.execute(
                "SELECT first_seq FROM proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
            seq = int(existing[0]) if existing else next_seq
            if existing is None:
                next_seq += 1
            self._apply(offset, row, seq)
            source_rows += 1
        after = self._signature(self.source)
        if before != after:
            db.rollback()
            raise ProposalLedgerSidecarError(
                "proposal ledger changed while rebuilding sidecar"
            )
        self._set_meta("schema", SCHEMA)
        self._set_meta("source_dev", after[0])
        self._set_meta("source_ino", after[1])
        self._set_meta("indexed_size", after[2])
        self._set_meta("source_mtime_ns", after[3])
        self._set_meta("first_record_sha256", self._first_record_digest(self.source))
        self._set_meta("next_seq", next_seq)
        db.commit()
        self._pending = 0
        return {
            "source_rows": source_rows,
            "proposals": next_seq,
            "indexed_size": after[2],
        }

    def _metadata_valid(self, sig: tuple[int, int, int, int]) -> bool:
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
            raise ProposalLedgerSidecarError("proposal source unavailable")
        try:
            sig = self._signature(self.source)
            if not self.path.exists():
                return self.rebuild()
            self._connect()
            if not self._metadata_valid(sig):
                return self.rebuild()

            indexed_size = int(self._meta("indexed_size") or 0)
            indexed_mtime = int(self._meta("source_mtime_ns") or 0)
            if indexed_size == sig[2]:
                if indexed_mtime != sig[3]:
                    return self.rebuild()
                return {
                    "source_rows": 0,
                    "proposals": self.count(),
                    "indexed_size": indexed_size,
                }

            before = self._signature(self.source)
            db = self._connect()
            next_seq = int(self._meta("next_seq") or 0)
            source_rows = 0
            end_offset = indexed_size
            db.execute("BEGIN")
            for offset, row, end in self._iter_from(self.source, indexed_size):
                proposal_id = str(row.get("proposal_id") or "")
                existing = db.execute(
                    "SELECT first_seq FROM proposals WHERE proposal_id=?",
                    (proposal_id,),
                ).fetchone()
                seq = int(existing[0]) if existing else next_seq
                if existing is None:
                    next_seq += 1
                self._apply(offset, row, seq)
                source_rows += 1
                end_offset = end
            after = self._signature(self.source)
            if before != after or end_offset != after[2]:
                db.rollback()
                raise ProposalLedgerSidecarError(
                    "proposal ledger changed while applying sidecar tail"
                )
            self._set_meta("indexed_size", after[2])
            self._set_meta("source_mtime_ns", after[3])
            self._set_meta("first_record_sha256", self._first_record_digest(self.source))
            self._set_meta("next_seq", next_seq)
            db.commit()
            self._pending = 0
            return {
                "source_rows": source_rows,
                "proposals": self.count(),
                "indexed_size": after[2],
            }
        except sqlite3.DatabaseError:
            return self.rebuild()

    def count(self) -> int:
        row = self._connect().execute(
            "SELECT COUNT(*) FROM proposals"
        ).fetchone()
        return int(row[0]) if row else 0

    def materialized_rows(
        self,
    ) -> list[tuple[str, int, int, str, str, str, str]]:
        return [
            (
                str(proposal_id),
                int(first_seq),
                int(offset),
                str(key or ""),
                str(status or ""),
                str(origin or ""),
                str(source_id or ""),
            )
            for proposal_id, first_seq, offset, key, status, origin, source_id
            in self._connect().execute(
                "SELECT proposal_id,first_seq,offset,idempotency_key,status,"
                "origin,source_proposal_id FROM proposals ORDER BY first_seq"
            )
        ]

    def note_append(
        self,
        *,
        offset: int,
        row: dict[str, Any],
        source_signature: tuple[int, int, int, int],
    ) -> None:
        if not self.path.exists():
            return
        try:
            self._connect()
            if (
                int(self._meta("source_dev") or -1),
                int(self._meta("source_ino") or -1),
            ) != source_signature[:2]:
                return
            next_seq = int(self._meta("next_seq") or 0)
            proposal_id = str(row.get("proposal_id") or "")
            existing = self._connect().execute(
                "SELECT first_seq FROM proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
            seq = int(existing[0]) if existing else next_seq
            if existing is None:
                next_seq += 1
            if self._pending == 0:
                self._connect().execute("BEGIN")
            self._apply(offset, row, seq)
            self._set_meta("indexed_size", source_signature[2])
            self._set_meta("source_mtime_ns", source_signature[3])
            self._set_meta("next_seq", next_seq)
            self._pending += 1
            if self._pending >= self.commit_every:
                self._connect().commit()
                self._pending = 0
        except sqlite3.DatabaseError:
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
    index = ProposalLedgerSidecar(args.source)
    try:
        result = index.rebuild() if args.rebuild else index.ensure()
        index.flush()
        print(json.dumps(
            {
                "schema": SCHEMA,
                "source": str(args.source),
                "index": str(index.path),
                **result,
            },
            sort_keys=True,
            separators=(",", ":"),
        ))
    finally:
        index.close(commit=True)


if __name__ == "__main__":
    main()
