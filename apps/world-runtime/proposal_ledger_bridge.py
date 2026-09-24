from __future__ import annotations

from typing import Any

from proposal_ledger import ProposalLedger


class ProposalLedgerBridge:
    """Compatibility bridge from legacy AI/audience proposal records."""

    def __init__(self, ledger: ProposalLedger) -> None:
        self.ledger = ledger

    def mirror_ai(self, proposal: dict[str, Any]) -> dict[str, Any]:
        source_id = str(proposal.get("proposal_id") or "").strip()
        if not source_id:
            raise ValueError("AI proposal_id is required")
        record = self.ledger.propose(
            origin="ai",
            proposer_id=str(proposal.get("actor_id") or "ai-router"),
            proposal_kind="world_mutation",
            payload={
                "action": proposal.get("action"),
                "gateway_text": proposal.get("gateway_text"),
                "confidence": proposal.get("confidence"),
                "reason": proposal.get("reason"),
                "model": proposal.get("model"),
            },
            source_proposal_id=source_id,
            metadata={"legacy_store": "ai-proposals.jsonl", **dict(proposal.get("metadata") or {})},
            idempotency_key=f"ai:{source_id}",
        )
        return record

    def mirror_audience(self, proposal: dict[str, Any]) -> dict[str, Any]:
        source_id = str(proposal.get("proposal_id") or "").strip()
        if not source_id:
            raise ValueError("audience proposal_id is required")
        record = self.ledger.propose(
            origin="audience",
            proposer_id="audience-aggregator",
            proposal_kind="world_mutation",
            payload={
                "gateway_text": proposal.get("gateway_text"),
                "rule_id": proposal.get("rule_id"),
                "reason": proposal.get("reason"),
            },
            source_proposal_id=source_id,
            metadata={"legacy_store": "audience-proposals.jsonl"},
            idempotency_key=f"audience:{source_id}",
        )
        return record

    def approve_by_source(self, origin: str, source_proposal_id: str, *, decided_by: str, reason: str | None = None) -> dict[str, Any]:
        row = self._find(origin, source_proposal_id)
        if row.get("status") == "approved":
            return row
        return self.ledger.approve(row["proposal_id"], decided_by=decided_by, reason=reason)

    def reject_by_source(self, origin: str, source_proposal_id: str, *, decided_by: str, reason: str) -> dict[str, Any]:
        row = self._find(origin, source_proposal_id)
        if row.get("status") == "rejected":
            return row
        return self.ledger.reject(row["proposal_id"], decided_by=decided_by, reason=reason)

    def commit_by_source(
        self,
        origin: str,
        source_proposal_id: str,
        *,
        decided_by: str,
        mutation_decision_id: str,
        world_event_id: str,
    ) -> dict[str, Any]:
        row = self._find(origin, source_proposal_id)
        if row.get("status") == "proposed":
            row = self.ledger.approve(row["proposal_id"], decided_by=decided_by, reason="approved for commit")
        if row.get("status") == "committed":
            return row
        return self.ledger.commit(
            row["proposal_id"],
            decided_by=decided_by,
            mutation_decision_id=mutation_decision_id,
            world_event_id=world_event_id,
        )

    def _find(self, origin: str, source_proposal_id: str) -> dict[str, Any]:
        origin = str(origin).strip().lower()
        source_proposal_id = str(source_proposal_id).strip()
        row = next((item for item in self.ledger.current()
                    if item.get("origin") == origin and item.get("source_proposal_id") == source_proposal_id), None)
        if row is None:
            raise KeyError("proposal not mirrored")
        return row
