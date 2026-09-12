from __future__ import annotations

from typing import Any

from plan_scheduler import PlanScheduler
from simulation_clock import SimulationClock
from world_event_scheduler import WorldEventScheduler


class WorldTickRunner:
    """Advance logical world time and evolve scheduled events plus active plans."""

    def __init__(
        self,
        clock: SimulationClock,
        scheduler: PlanScheduler,
        event_scheduler: WorldEventScheduler | None = None,
    ) -> None:
        self.clock = clock
        self.scheduler = scheduler
        self.event_scheduler = event_scheduler

    def tick(self) -> dict[str, Any]:
        before = self.clock.state()
        if before.paused:
            return {
                "advanced": False,
                "clock": before.as_dict(),
                "events": [],
                "plans": [],
            }

        after = self.clock.advance()

        # Global/scheduled events fire first. That ordering is deliberate: a
        # weather/state event due at tick N becomes visible to plans executed
        # in the same logical tick N.
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
            "plans": results,
        }
