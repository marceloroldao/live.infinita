from __future__ import annotations

from typing import Any

from conditional_event_scheduler import ConditionalEventScheduler
from plan_arbiter import PlanArbiter
from plan_scheduler import PlanScheduler
from simulation_clock import SimulationClock
from world_event_scheduler import WorldEventScheduler


class WorldTickRunner:
    """Advance logical world time and evolve events plus active plans."""

    def __init__(
        self,
        clock: SimulationClock,
        scheduler: PlanScheduler,
        event_scheduler: WorldEventScheduler | None = None,
        conditional_event_scheduler: ConditionalEventScheduler | None = None,
        plan_arbiter: PlanArbiter | None = None,
        npc_need_scheduler: Any | None = None,
        npc_need_dynamics: Any | None = None,
        npc_need_outcomes: Any | None = None,
    ) -> None:
        self.clock = clock
        self.scheduler = scheduler
        self.event_scheduler = event_scheduler
        self.conditional_event_scheduler = conditional_event_scheduler
        self.npc_need_scheduler = npc_need_scheduler
        self.npc_need_dynamics = npc_need_dynamics
        self.npc_need_outcomes = npc_need_outcomes
        resume_evaluator = getattr(scheduler, "assess_resume", None)
        self.plan_arbiter = plan_arbiter or PlanArbiter(scheduler.ledger, resume_evaluator=resume_evaluator)

    def tick(self) -> dict[str, Any]:
        before = self.clock.state()
        if before.paused:
            return {
                "advanced": False,
                "clock": before.as_dict(),
                "events": [],
                "conditional_events": [],
                "npc_need_dynamics": [],
                "npc_needs": [],
                "plan_replanning": [],
                "plan_arbitration": {
                    "preemptions": [],
                    "resumptions": [],
                    "replans": [],
                    "cancellations": [],
                },
                "plans": [],
                "npc_need_outcomes": [],
            }

        after = self.clock.advance()

        event_results: list[dict[str, Any]] = []
        if self.event_scheduler is not None:
            for row in self.event_scheduler.fire_due(after.tick):
                event_results.append({
                    "scheduled_event_id": row.get("scheduled_event_id"),
                    "status": row.get("status"),
                    "due_tick": row.get("due_tick"),
                    "fire_count": row.get("fire_count"),
                    "last_world_event_id": row.get("last_world_event_id"),
                    "last_mutation_decision_id": row.get("last_mutation_decision_id"),
                })

        conditional_results: list[dict[str, Any]] = []
        if self.conditional_event_scheduler is not None:
            for row in self.conditional_event_scheduler.evaluate_tick(after.tick):
                conditional_results.append({
                    "conditional_event_id": row.get("conditional_event_id"),
                    "effect_kind": row.get("effect_kind"),
                    "status": row.get("status"),
                    "condition_value": row.get("last_condition_value"),
                    "fire_count": row.get("fire_count"),
                    "last_fired_tick": row.get("last_fired_tick"),
                    "last_world_event_id": row.get("last_world_event_id"),
                    "last_mutation_decision_id": row.get("last_mutation_decision_id"),
                    "last_proposal_id": row.get("last_proposal_id"),
                    "last_plan_id": row.get("last_plan_id"),
                })

        need_dynamics_results: list[dict[str, Any]] = []
        if self.npc_need_dynamics is not None:
            for row in self.npc_need_dynamics.advance_tick(after.tick):
                need_dynamics_results.append({
                    "npc_id": row.get("npc_id"),
                    "tick": row.get("tick"),
                    "before": row.get("before"),
                    "after": row.get("after"),
                })

        need_results: list[dict[str, Any]] = []
        if self.npc_need_scheduler is not None:
            for row in self.npc_need_scheduler.evaluate_tick(after.tick):
                need_results.append({
                    "npc_id": row.get("npc_id"),
                    "need": row.get("need"),
                    "severity": row.get("severity"),
                    "priority": row.get("priority"),
                    "utility": row.get("utility"),
                    "status": row.get("status"),
                    "proposal_id": row.get("proposal_id"),
                    "plan_id": row.get("plan_id"),
                })

        replan_results: list[dict[str, Any]] = []
        replan_all = getattr(self.scheduler, "replan_all", None)
        if callable(replan_all):
            for row in replan_all():
                replan_results.append({
                    "plan_id": row.get("plan_id"),
                    "status": row.get("status"),
                    "plan_revision": row.get("plan_revision", 0),
                    "next_step_index": row.get("next_step_index", 0),
                    "last_error": row.get("last_error"),
                })

        arbitration = self.plan_arbiter.reconcile()
        results: list[dict[str, Any]] = []
        for record in arbitration.get("runnable", []):
            plan_id = str(record.get("plan_id") or "").strip()
            if not plan_id:
                continue
            result = self.scheduler.tick(plan_id, logical_tick=after.tick)
            results.append({
                "plan_id": plan_id,
                "actor_entity_id": result.get("actor_entity_id"),
                "priority": result.get("priority", 0),
                "plan_revision": result.get("plan_revision", 0),
                "status": result.get("status"),
                "next_step_index": result.get("next_step_index"),
                "started_logical_tick": result.get("started_logical_tick"),
                "completed_logical_tick": result.get("completed_logical_tick"),
                "preemption_count": result.get("preemption_count", 0),
                "replan_count": result.get("replan_count", 0),
                "last_world_event_id": result.get("last_world_event_id"),
                "last_mutation_decision_id": result.get("last_mutation_decision_id"),
            })

        outcome_results: list[dict[str, Any]] = []
        if self.npc_need_outcomes is not None:
            for row in self.npc_need_outcomes.process_completed():
                outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
                outcome_results.append({
                    "plan_id": row.get("plan_id"),
                    "proposal_id": row.get("proposal_id"),
                    "npc_id": row.get("npc_id"),
                    "need": row.get("need"),
                    "status": row.get("status"),
                    "before": outcome.get("before"),
                    "after": outcome.get("after"),
                    "amount": outcome.get("amount"),
                    "strategy_experience": row.get("strategy_experience"),
                })

        return {
            "advanced": True,
            "clock": after.as_dict(),
            "events": event_results,
            "conditional_events": conditional_results,
            "npc_need_dynamics": need_dynamics_results,
            "npc_needs": need_results,
            "plan_replanning": replan_results,
            "plan_arbitration": {
                "preemptions": arbitration.get("preemptions", []),
                "resumptions": arbitration.get("resumptions", []),
                "replans": arbitration.get("replans", []),
                "cancellations": arbitration.get("cancellations", []),
            },
            "plans": results,
            "npc_need_outcomes": outcome_results,
        }
