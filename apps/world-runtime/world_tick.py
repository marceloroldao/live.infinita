from __future__ import annotations

from typing import Any

from plan_scheduler import PlanScheduler
from simulation_clock import SimulationClock


class WorldTickRunner:
    """Advance logical world time and execute one step per active plan."""

    def __init__(self, clock: SimulationClock, scheduler: PlanScheduler) -> None:
        self.clock = clock
        self.scheduler = scheduler

    def tick(self) -> dict[str, Any]:
        before = self.clock.state()
        if before.paused:
            return {
                "advanced": False,
                "clock": before.as_dict(),
                "plans": [],
            }

        after = self.clock.advance()
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
            "plans": results,
        }
