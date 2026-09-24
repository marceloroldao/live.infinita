from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.spatial import AgentIntentResolver, DeterministicIntentPlanner, IntentPlan, MutationPrincipal
from mutation_gate_service import GuardedMutationService


@dataclass(frozen=True)
class PlanExecutionResult:
    status: str
    completed_steps: int
    total_steps: int
    world_event_ids: tuple[str, ...]
    mutation_decision_ids: tuple[str, ...]
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "world_event_ids": list(self.world_event_ids),
            "mutation_decision_ids": list(self.mutation_decision_ids),
            "reason": self.reason,
        }


class DeterministicIntentPlanExecutor:
    """Execute one precomputed intent plan through resolver + Mutation Gate.

    Each step is revalidated against authoritative cold state immediately before
    execution. No step is skipped or guessed. If state diverges, execution stops
    with status=stale. Policy rejection stops with status=rejected.
    """

    def __init__(
        self,
        planner: DeterministicIntentPlanner,
        resolver: AgentIntentResolver,
        guarded_mutations: GuardedMutationService,
    ) -> None:
        self.planner = planner
        self.resolver = resolver
        self.guarded = guarded_mutations

    def execute(
        self,
        plan: IntentPlan,
        *,
        principal: MutationPrincipal | dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> PlanExecutionResult:
        event_ids: list[str] = []
        decision_ids: list[str] = []
        total = len(plan.steps)

        for index in range(total):
            try:
                step = self.planner.revalidate_step(plan, index)
            except ValueError as exc:
                return PlanExecutionResult("stale", index, total, tuple(event_ids), tuple(decision_ids), str(exc))

            try:
                resolved = self.resolver.resolve(step.intent)
            except ValueError as exc:
                return PlanExecutionResult("invalid", index, total, tuple(event_ids), tuple(decision_ids), str(exc))

            step_context = {
                **dict(context or {}),
                "intent_plan": {
                    "intent_type": plan.intent_type,
                    "step_index": index,
                    "total_steps": total,
                    "step_kind": step.kind,
                    "goal_region_id": plan.goal_region_id,
                    "region_path": list(plan.region_path),
                },
            }
            result = self.guarded.commit(
                list(resolved.operations),
                principal=principal,
                context=step_context,
                narration=f"intent-plan step {index + 1}/{total}: {resolved.rationale}",
            )
            audit = result.get("audit") or {}
            decision_id = str(audit.get("mutation_decision_id") or "").strip()
            if decision_id:
                decision_ids.append(decision_id)
            if not result.get("ok"):
                reason = str((result.get("decision") or {}).get("reason") or "mutation rejected")
                return PlanExecutionResult("rejected", index, total, tuple(event_ids), tuple(decision_ids), reason)

            event = result.get("event") or {}
            event_id = str(event.get("event_id") or "").strip()
            if event_id:
                event_ids.append(event_id)

        return PlanExecutionResult("completed", total, total, tuple(event_ids), tuple(decision_ids), None)
