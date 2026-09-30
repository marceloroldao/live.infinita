from __future__ import annotations

import json
import os
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any


class ProposalLedgerError(ValueError):
    pass


class ProposalLedger:
    """Append-only unified proposal lifecycle ledger.

    Canonical lifecycle:
      proposed -> approved -> committed
      proposed -> rejected
      proposed/approved -> expired

    The ledger is not authoritative world replay. It records intent lifecycle and
    links committed proposals to mutation decisions and world events.
    """

    TERMINAL = frozenset({"committed", "rejected", "expired"})
    ALLOWED = {
        "proposed": frozenset({"approved", "rejected", "expired"}),
        "approved": frozenset({"committed", "rejected", "expired"}),
        "committed": frozenset(),
        "rejected": frozenset(),
        "expired": frozenset(),
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._view_by_id: dict[str, dict[str, Any]] | None = None
        self._view_order: list[str] = []
        self._view_idempotency: dict[str, str] = {}
        self._view_signature: tuple[int, int, int, int] | None = None

    def _signature(self) -> tuple[int, int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def _iter_current(self):
        if not self.path.exists():
            return
        with self.path.open("rb") as fh:
            while True:
                offset = fh.tell()
                raw = fh.readline()
                if not raw:
                    break
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    if fh.read(1):
                        raise ProposalLedgerError(
                            f"corrupt proposal ledger at byte {offset}"
                        ) from exc
                    raise ProposalLedgerError(
                        f"torn proposal ledger tail at byte {offset}"
                    ) from exc
                if isinstance(value, dict):
                    yield value

    def _ensure_view(self) -> None:
        if self._view_by_id is not None and self._view_signature == self._signature():
            return
        for _ in range(3):
            before = self._signature()
            latest: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for row in self._iter_current():
                proposal_id = str(row.get("proposal_id") or "").strip()
                if not proposal_id:
                    continue
                if proposal_id not in latest:
                    order.append(proposal_id)
                latest[proposal_id] = row
            after = self._signature()
            if before == after:
                keys: dict[str, str] = {}
                for proposal_id in order:
                    key = str(latest[proposal_id].get("idempotency_key") or "")
                    if key:
                        keys.setdefault(key, proposal_id)
                self._view_by_id = latest
                self._view_order = order
                self._view_idempotency = keys
                self._view_signature = after
                return
        raise ProposalLedgerError("proposal ledger changed while rebuilding current state")

    def _compaction_manifest(self) -> dict[str, Any] | None:
        manifest_path = self.path.with_name(self.path.name + ".compaction.json")
        if not manifest_path.exists():
            return None
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ProposalLedgerError("proposal compaction manifest invalid") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != "live-infinita-hot-ledger-compaction/v1"
            or value.get("kind") != "proposals"
            or value.get("source") != self.path.name
            or not isinstance(value.get("archive"), str)
            or type(value.get("latest_rows")) is not int
            or int(value["latest_rows"]) < 1
        ):
            raise ProposalLedgerError("proposal compaction manifest invalid")
        return value

    @staticmethod
    def _read_archive_history(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("rb") as fh:
            for line_number, raw in enumerate(fh, start=1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ProposalLedgerError(
                        f"proposal archive corrupt at line {line_number}"
                    ) from exc
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def history(self) -> list[dict[str, Any]]:
        current_rows = list(self._iter_current())
        manifest = self._compaction_manifest()
        if manifest is None:
            return current_rows
        archive = self.path.parent / str(manifest["archive"])
        if not archive.is_file() or archive.is_symlink():
            raise ProposalLedgerError("proposal compaction archive unavailable")
        boundary = int(manifest["latest_rows"])
        if len(current_rows) < boundary:
            raise ProposalLedgerError("proposal compact snapshot truncated")
        return self._read_archive_history(archive) + current_rows[boundary:]

    def current(self) -> list[dict[str, Any]]:
        self._ensure_view()
        assert self._view_by_id is not None
        return [deepcopy(self._view_by_id[proposal_id]) for proposal_id in self._view_order]

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        row = self._view_by_id.get(str(proposal_id or "").strip())
        return deepcopy(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        proposal_id = self._view_idempotency.get(str(key or "").strip())
        row = self._view_by_id.get(proposal_id) if proposal_id else None
        return deepcopy(row) if row is not None else None

    def _append(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = (
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        before = self._signature()
        cached = self._view_by_id is not None and self._view_signature == before
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            written = os.write(fd, payload)
            if written != len(payload):
                raise ProposalLedgerError(
                    f"short proposal-ledger append: {written}/{len(payload)} bytes"
                )
            os.fsync(fd)
        except BaseException:
            self._view_by_id = None
            raise
        finally:
            os.close(fd)

        after = self._signature()
        expected_size = (before[2] if before else 0) + len(payload)
        if cached and after is not None and after[2] == expected_size and (
            before is None or after[:2] == before[:2]
        ):
            assert self._view_by_id is not None
            proposal_id = str(record.get("proposal_id") or "").strip()
            if proposal_id:
                previous = self._view_by_id.get(proposal_id)
                old_key = str(previous.get("idempotency_key") or "") if previous else ""
                key = str(record.get("idempotency_key") or "")
                if previous is not None and old_key != key:
                    self._view_by_id = None
                else:
                    if previous is None:
                        self._view_order.append(proposal_id)
                    self._view_by_id[proposal_id] = deepcopy(record)
                    if key:
                        self._view_idempotency.setdefault(key, proposal_id)
            self._view_signature = after
        else:
            self._view_by_id = None
        return record

    def propose(
        self,
        *,
        origin: str,
        proposer_id: str,
        proposal_kind: str,
        payload: dict[str, Any],
        source_proposal_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        origin = str(origin or "").strip().lower()
        proposer_id = str(proposer_id or "").strip()
        proposal_kind = str(proposal_kind or "").strip().lower()
        if not origin or not proposer_id or not proposal_kind:
            raise ProposalLedgerError("origin, proposer_id and proposal_kind are required")
        if not isinstance(payload, dict):
            raise ProposalLedgerError("payload must be an object")

        if idempotency_key:
            key = str(idempotency_key).strip()
            existing = self.get_by_idempotency_key(key)
            if existing is not None:
                return existing
        else:
            key = None

        now = time.time()
        proposal_id = f"pr_{int(now * 1000)}_{uuid.uuid4().hex[:10]}"
        return self._append({
            "proposal_schema": "proposal_ledger_v1",
            "proposal_id": proposal_id,
            "source_proposal_id": str(source_proposal_id or "").strip() or None,
            "origin": origin,
            "proposer_id": proposer_id,
            "proposal_kind": proposal_kind,
            "status": "proposed",
            "payload": deepcopy(payload),
            "metadata": deepcopy(metadata or {}),
            "idempotency_key": key,
            "created_at_unix": now,
            "updated_at_unix": now,
        })

    def transition(
        self,
        proposal_id: str,
        status: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
        mutation_decision_id: str | None = None,
        world_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError("proposal not found")
        current_status = str(current.get("status") or "")
        status = str(status or "").strip().lower()
        if status not in self.ALLOWED.get(current_status, frozenset()):
            raise ProposalLedgerError(f"invalid transition: {current_status} -> {status}")
        if status == "committed":
            if not mutation_decision_id:
                raise ProposalLedgerError("committed proposal requires mutation_decision_id")
            if not world_event_id:
                raise ProposalLedgerError("committed proposal requires world_event_id")

        record = deepcopy(current)
        record["status"] = status
        record["updated_at_unix"] = time.time()
        record["decided_by"] = str(decided_by or "").strip() or None
        record["decision_reason"] = str(reason or "")[:1000] or None
        if mutation_decision_id is not None:
            record["mutation_decision_id"] = str(mutation_decision_id).strip() or None
        if world_event_id is not None:
            record["world_event_id"] = str(world_event_id).strip() or None
        if metadata:
            merged = dict(record.get("metadata") or {})
            merged.update(deepcopy(metadata))
            record["metadata"] = merged
        return self._append(record)

    def approve(self, proposal_id: str, *, decided_by: str, reason: str | None = None) -> dict[str, Any]:
        return self.transition(proposal_id, "approved", decided_by=decided_by, reason=reason)

    def reject(self, proposal_id: str, *, decided_by: str, reason: str) -> dict[str, Any]:
        return self.transition(proposal_id, "rejected", decided_by=decided_by, reason=reason)

    def expire(self, proposal_id: str, *, reason: str = "expired") -> dict[str, Any]:
        return self.transition(proposal_id, "expired", decided_by="system", reason=reason)

    def commit(
        self,
        proposal_id: str,
        *,
        decided_by: str,
        mutation_decision_id: str,
        world_event_id: str,
    ) -> dict[str, Any]:
        return self.transition(
            proposal_id,
            "committed",
            decided_by=decided_by,
            mutation_decision_id=mutation_decision_id,
            world_event_id=world_event_id,
        )
