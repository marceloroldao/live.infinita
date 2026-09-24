from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_intent_service import AgentIntentService
from proposal_ledger import ProposalLedger, ProposalLedgerError


class AgentIntentCoordinator:
    """Proposal-ledger lifecycle for semantic agent intents.

    Intents never commit on submission. They become proposal_ledger_v1 records,
    require an explicit approval transition, then resolve through AgentIntentService
    and MutationGate. Successful commits link proposal -> decision -> world event.
    """

    def __init__(self, ledger: ProposalLedger, intent_service: AgentIntentService) -> None:
        self.ledger = ledger
        self.intent_service = intent_service

    def propose(
        self,
        intent: dict[str, Any],
        *,
        origin: str,
        proposer_id: str,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        # Resolve early for structural validation only. This does not mutate state
        # and does not authorize the proposer.
        resolved = self.intent_service.resolve(intent)
        return self.ledger.propose(
            origin=origin,
            proposer_id=proposer_id,
            proposal_kind="agent_intent",
            payload={"intent": deepcopy(intent), "resolved_preview": resolved},
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    def reject(self, proposal_id: str, *, decided_by: str, reason: str) -> dict[str, Any]:
        return self.ledger.reject(proposal_id, decided_by=decided_by, reason=reason)

    def approve_and_commit(
        self,
        proposal_id: str,
        *,
        approved_by: str,
        principal: dict[str, Any],
        context: dict[str, Any] | None = None,
        narration: str = "",
    ) -> dict[str, Any]:
        current = self.ledger.get(proposal_id)
        if current is None:
            raise KeyError("proposal not found")
        if current.get("proposal_kind") != "agent_intent":
            raise ProposalLedgerError("proposal is not an agent_intent")
        if current.get("status") != "proposed":
            raise ProposalLedgerError("agent intent proposal is not proposed")

        approved = self.ledger.approve(proposal_id, decided_by=approved_by)
        payload = approved.get("payload") if isinstance(approved.get("payload"), dict) else {}
        intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else None
        if intent is None:
            self.ledger.reject(proposal_id, decided_by="system", reason="missing semantic intent payload")
            raise ProposalLedgerError("missing semantic intent payload")

        commit_context = deepcopy(context or {})
        commit_context.update({
            "proposal_id": proposal_id,
            "proposal_kind": "agent_intent",
            "approved_by": approved_by,
        })
        result = self.intent_service.commit_resolved(
            intent,
            principal=principal,
            context=commit_context,
            narration=narration,
        )
        if not result.get("ok"):
            reason = str((result.get("decision") or {}).get("reason") or "mutation gate rejected intent")
            rejected = self.ledger.reject(proposal_id, decided_by="mutation_gate", reason=reason)
            return {"ok": False, "proposal": rejected, "mutation": result}

        audit = result.get("audit") or {}
        event = result.get("event") or {}
        mutation_decision_id = str(audit.get("mutation_decision_id") or "").strip()
        world_event_id = str(event.get("event_id") or "").strip()
        if not mutation_decision_id or not world_event_id:
            raise ProposalLedgerError("accepted intent commit lacks decision/event linkage")

        committed = self.ledger.commit(
            proposal_id,
            decided_by=approved_by,
            mutation_decision_id=mutation_decision_id,
            world_event_id=world_event_id,
        )
        return {"ok": True, "proposal": committed, "mutation": result}
