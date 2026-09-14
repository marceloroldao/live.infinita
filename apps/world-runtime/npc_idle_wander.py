from __future__ import annotations

import math
import zlib
from typing import Any

from plan_scheduler import PlanScheduler


class NpcIdleWander:
    """Schedule low-priority deterministic walking when an NPC has no active goal.

    This is deliberately below every need-driven priority. It never competes with
    safety/energy/social/curiosity plans: as soon as a real need or plan exists,
    idle wandering yields. Waypoints are derived from region topology, so no
    random generator or LLM is required and replay remains deterministic.
    """

    def __init__(
        self,
        plan_scheduler: PlanScheduler,
        *,
        npc_ids: list[str],
        interval_ticks: int = 8,
        priority: int = 25,
    ) -> None:
        self.plans = plan_scheduler
        self.npc_ids = tuple(sorted({str(value).strip() for value in npc_ids if str(value).strip()}))
        self.interval_ticks = max(2, int(interval_ticks))
        self.priority = int(priority)

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.plans.planner.store.get_entity(entity_id)

    def _has_active_plan(self, npc_id: str) -> bool:
        for record in self.plans.ledger.active():
            if str(record.get("actor_entity_id") or "") == npc_id:
                return True
        return False

    def _select_region(self, entity: dict[str, Any], bucket: int):
        regions = self.plans.planner.regions
        current_id = str(entity.get("region_id") or "").strip()
        current = regions.get(current_id)
        if current is None:
            return None

        # Mostly roam inside the current region. Every fourth idle decision may
        # cross one topology edge, which keeps the world alive without making Nov
        # ping-pong across the entire map.
        neighbors = [region_id for region_id in sorted(current.neighbors) if regions.get(region_id) is not None]
        if neighbors and bucket % 4 == 3:
            return regions.get(neighbors[(bucket // 4) % len(neighbors)])
        return current

    @staticmethod
    def _waypoint(npc_id: str, region: Any, bucket: int) -> dict[str, float]:
        seed = zlib.crc32(npc_id.encode("utf-8")) & 0xFFFFFFFF
        phase_index = (bucket + seed) % 12
        angle = (float(phase_index) / 12.0) * math.tau
        radius = float(region.radius) * (0.34 + 0.08 * float((bucket + seed) % 3))
        return {
            "x": float(region.center[0]) + math.cos(angle) * radius,
            "y": float(region.center[1]) + math.sin(angle) * radius * 0.60,
        }

    def evaluate_tick(self, tick: int, *, blocked_npc_ids: set[str] | None = None) -> list[dict[str, Any]]:
        tick = int(tick)
        if tick <= 0 or tick % self.interval_ticks != 0:
            return []

        blocked = {str(value) for value in (blocked_npc_ids or set())}
        bucket = tick // self.interval_ticks
        results: list[dict[str, Any]] = []
        for npc_id in self.npc_ids:
            entity = self._entity(npc_id)
            if entity is None:
                continue
            if npc_id in blocked:
                results.append({"npc_id": npc_id, "tick": tick, "status": "need_active"})
                continue
            if self._has_active_plan(npc_id):
                results.append({"npc_id": npc_id, "tick": tick, "status": "busy"})
                continue

            region = self._select_region(entity, bucket)
            if region is None:
                results.append({"npc_id": npc_id, "tick": tick, "status": "no_region"})
                continue

            position = self._waypoint(npc_id, region, bucket)
            intent = {
                "intent": "move_to_position",
                "actor_entity_id": npc_id,
                "position": position,
                "region_id": region.id,
                "idle_wander": True,
            }
            principal = {
                "source": "npc_idle",
                "actor_id": npc_id,
                "authority": "entity_agent",
                "subject_entity_id": npc_id,
            }
            plan = self.plans.schedule(
                intent=intent,
                principal=principal,
                proposer_id=f"npc-idle:{npc_id}",
                proposal_id=None,
                idempotency_key=f"npc-idle:{npc_id}:{bucket}",
                priority=self.priority,
            )
            results.append({
                "npc_id": npc_id,
                "tick": tick,
                "status": "scheduled",
                "plan_id": plan.get("plan_id"),
                "region_id": region.id,
                "position": position,
                "priority": self.priority,
            })
        return results
