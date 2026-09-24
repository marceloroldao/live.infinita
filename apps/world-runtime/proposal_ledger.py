from __future__ import annotations

import json
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

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def current(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in self.history():
            proposal_id = str(row.get("proposal_id") or "").strip()
            if not proposal_id:
                continue
            if proposal_id not in latest:
                order.append(proposal_id)
            latest[proposal_id] = row
        return [latest[proposal_id] for proposal_id in order]

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        proposal_id = str(proposal_id or "").strip()
        return next((row for row in self.current() if row.get("proposal_id") == proposal_id), None)

    def _append(self, record: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
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
            for row in self.current():
                if row.get("idempotency_key") == key:
                    return row
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
