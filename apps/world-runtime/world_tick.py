from __future__ import annotations

from typing import Any

from conditional_event_scheduler import ConditionalEventScheduler
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
    ) -> None:
        self.clock = clock
        self.scheduler = scheduler
        self.event_scheduler = event_scheduler
        self.conditional_event_scheduler = conditional_event_scheduler

    def tick(self) -> dict[str, Any]:
        before = self.clock.state()
        if before.paused:
            return {
                "advanced": False,
                "clock": before.as_dict(),
                "events": [],
                "conditional_events": [],
                "plans": [],
            }

        after = self.clock.advance()

        # Time-scheduled global events fire first.
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

        # Conditional events observe the authoritative state after time events
        # of this tick and before character plans. This makes ordering stable:
        # clock -> scheduled events -> conditional events -> plans.
        conditional_results: list[dict[str, Any]] = []
        if self.conditional_event_scheduler is not None:
            for row in self.conditional_event_scheduler.evaluate_tick(after.tick):
                conditional_results.append({
                    "conditional_event_id": row.get("conditional_event_id"),
                    "status": row.get("status"),
                    "condition_value": row.get("last_condition_value"),
                    "fire_count": row.get("fire_count"),
                    "last_fired_tick": row.get("last_fired_tick"),
                    "last_world_event_id": row.get("last_world_event_id"),
                    "last_mutation_decision_id": row.get("last_mutation_decision_id"),
                })

        active = sorted(
            self.scheduler.ledger.active(),
            key=lambda row: str(row.get("plan_id") or ""),
        )
        results: list[dict[str, Any]] = []
        for record in active:
            plan_id = str(record.get("plan_id") or "").strip()
            if not plan_id:
                continue
            result = self.scheduler.tick(plan_id)
            results.append({
                "plan_id": plan_id,
                "status": result.get("status"),
                "next_step_index": result.get("next_step_index"),
                "last_world_event_id": result.get("last_world_event_id"),
                "last_mutation_decision_id": result.get("last_mutation_decision_id"),
            })

        return {
            "advanced": True,
            "clock": after.as_dict(),
            "events": event_results,
            "conditional_events": conditional_results,
            "plans": results,
        }
