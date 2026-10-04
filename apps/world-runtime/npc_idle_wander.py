from __future__ import annotations

import math
import zlib
from typing import Any

from plan_scheduler import PlanScheduler
from npc_environmental_exploration import choose_local_region


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
        interval_ticks: int = 4,
        priority: int = 25,
        environmental_provider: Any | None = None,
    ) -> None:
        self.plans = plan_scheduler
        self.npc_ids = tuple(sorted({str(value).strip() for value in npc_ids if str(value).strip()}))
        self.interval_ticks = max(2, int(interval_ticks))
        self.priority = int(priority)
        self.environmental_provider = environmental_provider
        self._environmental_stimulus: dict[str, Any] = {}
        self._environmental_decision: dict[str, Any] = {}

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.plans.planner.store.get_entity(entity_id)

    def _has_active_plan(self, npc_id: str) -> bool:
        # The ledger keeps a creation-ordered active view; avoid copying its
        # plan payloads when the idle scheduler needs only an actor membership
        # check. Retain compatibility with external/fake ledger implementations.
        indexed = getattr(self.plans.ledger, "has_active_plan_for_actor", None)
        if callable(indexed):
            return bool(indexed(npc_id))
        for record in self.plans.ledger.active():
            if str(record.get("actor_entity_id") or "") == npc_id:
                return True
        return False

    @staticmethod
    def _previous_region(entity: dict[str, Any], current_id: str) -> str:
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        navigation = properties.get("navigation") if isinstance(properties.get("navigation"), dict) else {}
        arrived = str(navigation.get("arrived_region_id") or "").strip()
        previous = str(navigation.get("previous_region_id") or "").strip()
        return previous if arrived == current_id else ""

    def _select_region(self, entity: dict[str, Any], bucket: int):
        self._environmental_decision = {}
        regions = self.plans.planner.regions
        current_id = str(entity.get("region_id") or "").strip()
        current = regions.get(current_id)
        if current is None:
            return None

        # Mostly roam inside the current region. Every fourth idle decision may
        # cross one topology edge. When the last idle arrival is still relevant,
        # avoid immediately returning through the same edge so deterministic
        # exploration cannot collapse into a two-region ping-pong.
        neighbors = [region_id for region_id in sorted(current.neighbors) if regions.get(region_id) is not None]
        if neighbors and bucket % 4 == 3:
            previous = self._previous_region(entity, current_id)
            choices = [region_id for region_id in neighbors if region_id != previous]
            if not choices:
                choices = neighbors
            baseline = choices[(bucket // 4) % len(choices)]
            target, self._environmental_decision = choose_local_region(
                choices, baseline, self._environmental_stimulus, bucket
            )
            return regions.get(target)
        return current

    @staticmethod
    def _waypoint(npc_id: str, region: Any, bucket: int) -> dict[str, float]:
        seed = zlib.crc32(npc_id.encode("utf-8")) & 0xFFFFFFFF
        # A 5/16 angular stride is coprime with 16, so consecutive idle goals are
        # intentionally separated instead of crawling around the circumference.
        phase_index = (bucket * 5 + seed) % 16
        angle = (float(phase_index) / 16.0) * math.tau
        radius = float(region.radius) * (0.44 + 0.08 * float((bucket + seed) % 3))
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

            self._environmental_stimulus = (
                self.environmental_provider() if callable(self.environmental_provider) else {}
            )
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
                "environmental_context": dict(self._environmental_decision),
            }
            current_id = str(entity.get("region_id") or "").strip()
            if region.id != current_id:
                intent["navigation_context"] = {
                    "previous_region_id": current_id,
                    "arrived_region_id": region.id,
                }
            principal = {
                "source": "npc_idle",
                "actor_id": npc_id,
                "authority": "entity_agent",
                "subject_entity_id": npc_id,
            }
            idem = f"npc-idle:{npc_id}:{bucket}"

            # Same-region idle motion is a regenerable one-step action. Execute
            # it directly through the guarded mutation path when supported, so
            # disposable control-plane plans do not force three durable plan
            # lifecycle appends (create/running/completed).
            execute_ephemeral = getattr(
                self.plans, "execute_ephemeral_one_step", None
            )
            if region.id == current_id and callable(execute_ephemeral):
                execution = execute_ephemeral(
                    intent=intent,
                    principal=principal,
                    logical_tick=tick,
                    idempotency_key=idem,
                    priority=self.priority,
                )
                if execution.get("status") != "requires_persistent":
                    results.append({
                        "npc_id": npc_id,
                        "tick": tick,
                        "status": execution.get("status"),
                        "plan_id": None,
                        "region_id": region.id,
                        "position": position,
                        "priority": self.priority,
                        "environmental_context": dict(self._environmental_decision),
                        "ephemeral": True,
                        "mutation_decision_id": execution.get(
                            "mutation_decision_id"
                        ),
                        "world_event_id": execution.get("world_event_id"),
                    })
                    continue

            plan = self.plans.schedule(
                intent=intent,
                principal=principal,
                proposer_id=f"npc-idle:{npc_id}",
                proposal_id=None,
                idempotency_key=idem,
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
                "environmental_context": dict(self._environmental_decision),
                "ephemeral": False,
            })
        return results
