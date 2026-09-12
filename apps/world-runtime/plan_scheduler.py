from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.spatial import (
    AgentIntentResolver,
    DeterministicIntentPlanner,
    IntentPlan,
    MutationPrincipal,
    PlanStep,
)
from mutation_gate_service import GuardedMutationService
from plan_ledger import PlanLedger


class PlanScheduler:
    """Execute at most one authoritative plan step per tick."""

    def __init__(
        self,
        ledger: PlanLedger,
        planner: DeterministicIntentPlanner,
        resolver: AgentIntentResolver,
        guarded_mutations: GuardedMutationService,
        proposal_ledger: Any | None = None,
    ) -> None:
        self.ledger = ledger
        self.planner = planner
        self.resolver = resolver
        self.guarded = guarded_mutations
        self.proposal_ledger = proposal_ledger

    @staticmethod
    def _principal(value: dict[str, Any]) -> MutationPrincipal:
        return MutationPrincipal.from_dict(value)

    @staticmethod
    def _rehydrate_plan(value: dict[str, Any]) -> IntentPlan:
        steps: list[PlanStep] = []
        for raw in value.get("steps", []):
            steps.append(PlanStep(
                int(raw["step_index"]),
                str(raw["kind"]),
                deepcopy(raw["intent"]),
                raw.get("expected_region_id"),
                raw.get("goal_region_id"),
            ))
        return IntentPlan(
            str(value.get("intent_type") or ""),
            value.get("actor_entity_id"),
            value.get("source_region_id"),
            value.get("goal_region_id"),
            tuple(str(v) for v in value.get("region_path", [])),
            tuple(steps),
        )

    def schedule(
        self,
        *,
        intent: dict[str, Any],
        principal: MutationPrincipal | dict[str, Any],
        proposer_id: str,
        proposal_id: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> dict[str, Any]:
        if isinstance(principal, MutationPrincipal):
            principal_dict = {
                "source": principal.source,
                "actor_id": principal.actor_id,
                "authority": principal.authority,
                "subject_entity_id": principal.subject_entity_id,
            }
        else:
            principal_dict = dict(principal)
            MutationPrincipal.from_dict(principal_dict)
        plan = self.planner.plan(intent)
        return self.ledger.create(
            proposal_id=proposal_id,
            proposer_id=proposer_id,
            principal=principal_dict,
            intent=intent,
            plan=plan.as_dict(),
            idempotency_key=idempotency_key,
            priority=int(priority),
            actor_entity_id=plan.actor_entity_id,
        )

    def _reject_proposal(self, record: dict[str, Any], reason: str) -> None:
        if self.proposal_ledger is None:
            return
        proposal_id = str(record.get("proposal_id") or "").strip()
        if not proposal_id:
            return
        proposal = self.proposal_ledger.get(proposal_id)
        if proposal is not None and proposal.get("status") == "approved":
            self.proposal_ledger.reject(proposal_id, decided_by="plan_scheduler", reason=reason)

    def _commit_proposal_if_complete(self, record: dict[str, Any]) -> None:
        if self.proposal_ledger is None or record.get("status") != "completed":
            return
        proposal_id = str(record.get("proposal_id") or "").strip()
        if not proposal_id:
            return
        proposal = self.proposal_ledger.get(proposal_id)
        if proposal is None or proposal.get("status") != "approved":
            return
        completed = list(record.get("completed_steps") or [])
        if not completed:
            return
        last = completed[-1]
        decision_id = str(last.get("mutation_decision_id") or "").strip()
        event_id = str(last.get("world_event_id") or "").strip()
        if decision_id and event_id:
            self.proposal_ledger.commit(
                proposal_id,
                decided_by="plan_scheduler",
                mutation_decision_id=decision_id,
                world_event_id=event_id,
            )

    def tick(self, plan_id: str) -> dict[str, Any]:
        record = self.ledger.get(plan_id)
        if record is None:
            raise KeyError("plan not found")
        status = str(record.get("status") or "")
        if status in self.ledger.TERMINAL:
            self._commit_proposal_if_complete(record)
            return record
        if status in {"waiting", "replanning"}:
            return record
        if status == "planned":
            record = self.ledger.transition(plan_id, "running")

        plan = self._rehydrate_plan(record["plan"])
        index = int(record.get("next_step_index", 0))
        if index >= len(plan.steps):
            record = self.ledger.transition(plan_id, "completed")
            self._commit_proposal_if_complete(record)
            return record

        try:
            step = self.planner.revalidate_step(plan, index)
        except ValueError as exc:
            return self.ledger.transition(plan_id, "replanning", last_error=str(exc))

        try:
            resolved = self.resolver.resolve(step.intent)
        except ValueError as exc:
            failed = self.ledger.transition(plan_id, "failed", last_error=str(exc))
            self._reject_proposal(failed, str(exc))
            return failed

        principal = self._principal(record["principal"])
        result = self.guarded.commit(
            list(resolved.operations),
            principal=principal,
            context={
                "plan_id": plan_id,
                "proposal_id": record.get("proposal_id"),
                "plan_priority": int(record.get("priority", 0)),
                "intent_plan": {
                    "intent_type": plan.intent_type,
                    "step_index": index,
                    "total_steps": len(plan.steps),
                    "step_kind": step.kind,
                    "goal_region_id": plan.goal_region_id,
                    "region_path": list(plan.region_path),
                },
            },
            narration=f"plan {plan_id} step {index + 1}/{len(plan.steps)}: {resolved.rationale}",
        )
        audit = result.get("audit") or {}
        decision_id = str(audit.get("mutation_decision_id") or "").strip() or None
        if not result.get("ok"):
            reason = str((result.get("decision") or {}).get("reason") or "mutation rejected")
            failed = self.ledger.transition(
                plan_id,
                "failed",
                last_error=reason,
                last_mutation_decision_id=decision_id,
            )
            self._reject_proposal(failed, reason)
            return failed

        event = result.get("event") or {}
        world = result.get("world") or {}
        event_id = str(event.get("event_id") or "").strip() or None
        state_hash = str(world.get("state_hash") or "").strip() or None
        updated = self.ledger.mark_step_completed(
            plan_id,
            step_index=index,
            mutation_decision_id=decision_id,
            world_event_id=event_id,
            state_hash=state_hash,
        )
        self._commit_proposal_if_complete(updated)
        return updated

    def tick_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for record in self.ledger.active():
            results.append(self.tick(str(record["plan_id"])))
        return results
