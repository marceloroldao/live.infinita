from __future__ import annotations

from copy import deepcopy
from typing import Any

from plan_scheduler import PlanScheduler
from proposal_ledger import ProposalLedger


class ConditionalPlanDispatcher:
    """Bridge a pre-authorized conditional rule into ProposalLedger + PlanScheduler.

    Scheduling a plan does not mutate world state. The created proposal is marked
    approved because the conditional rule itself was registered as an authorized
    world policy. Every eventual plan step still passes MutationGate through the
    normal PlanScheduler execution path.
    """

    def __init__(self, proposal_ledger: ProposalLedger, plan_scheduler: PlanScheduler) -> None:
        self.proposal_ledger = proposal_ledger
        self.plan_scheduler = plan_scheduler

    def dispatch(
        self,
        *,
        conditional_event_id: str,
        tick: int,
        fire_index: int,
        intent: dict[str, Any],
        principal: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conditional_event_id = str(conditional_event_id or "").strip()
        if not conditional_event_id:
            raise ValueError("conditional_event_id is required")
        metadata = deepcopy(metadata or {})
        proposer_id = f"conditional:{conditional_event_id}"
        idem = f"conditional-intent:{conditional_event_id}:{int(fire_index)}"
        proposal = self.proposal_ledger.propose(
            origin="conditional_event",
            proposer_id=proposer_id,
            proposal_kind="agent_intent",
            payload={"intent": deepcopy(intent)},
            metadata={
                "conditional_event_id": conditional_event_id,
                "fired_at_tick": int(tick),
                "fire_index": int(fire_index),
                **metadata,
            },
            idempotency_key=idem,
        )
        status = str(proposal.get("status") or "")
        if status == "proposed":
            proposal = self.proposal_ledger.approve(
                str(proposal["proposal_id"]),
                decided_by=f"conditional_policy:{conditional_event_id}",
                reason="pre-authorized conditional rule fired",
            )
        elif status not in {"approved", "committed"}:
            raise ValueError(f"conditional proposal is not schedulable: {status}")

        priority = int(metadata.get("plan_priority", 0) or 0)
        plan = self.plan_scheduler.schedule(
            intent=deepcopy(intent),
            principal=deepcopy(principal),
            proposer_id=proposer_id,
            proposal_id=str(proposal["proposal_id"]),
            idempotency_key=f"conditional-plan:{proposal['proposal_id']}",
            priority=priority,
        )
        return {"proposal": proposal, "plan": plan}
