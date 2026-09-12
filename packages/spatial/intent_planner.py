from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .cold_store import FileRegionColdStore
from .regions import RegionCatalog


class IntentPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PlanStep:
    step_index: int
    kind: str
    intent: dict[str, Any]
    expected_region_id: str | None
    goal_region_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "kind": self.kind,
            "intent": deepcopy(self.intent),
            "expected_region_id": self.expected_region_id,
            "goal_region_id": self.goal_region_id,
        }


@dataclass(frozen=True)
class IntentPlan:
    intent_type: str
    actor_entity_id: str | None
    source_region_id: str | None
    goal_region_id: str | None
    region_path: tuple[str, ...]
    steps: tuple[PlanStep, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "actor_entity_id": self.actor_entity_id,
            "source_region_id": self.source_region_id,
            "goal_region_id": self.goal_region_id,
            "region_path": list(self.region_path),
            "steps": [step.as_dict() for step in self.steps],
        }


class DeterministicIntentPlanner:
    """Expand semantic intents into deterministic, revalidatable steps.

    v1 decomposes movement intents across explicit region topology. Non-movement
    intents remain one semantic step and are resolved immediately before execution.
    Planning never mutates world state and never grants authority.
    """

    def __init__(self, store: FileRegionColdStore, regions: RegionCatalog) -> None:
        self.store = store
        self.regions = regions

    def _entity(self, entity_id: str) -> dict[str, Any]:
        entity = self.store.get_entity(entity_id)
        if entity is None:
            raise IntentPlanError(f"entity not found: {entity_id}")
        return entity

    @staticmethod
    def _required(value: Any, field: str) -> str:
        result = str(value or "").strip()
        if not result:
            raise IntentPlanError(f"{field} is required")
        return result

    def _region(self, region_id: str):
        region = self.regions.get(region_id)
        if region is None:
            raise IntentPlanError(f"region not found: {region_id}")
        return region

    def _path(self, source: str, goal: str) -> tuple[str, ...]:
        self._region(source)
        self._region(goal)
        route = self.regions.route(source, goal)
        if not route:
            raise IntentPlanError(f"no region path: {source} -> {goal}")
        return tuple(route)

    def plan(self, intent: dict[str, Any]) -> IntentPlan:
        if not isinstance(intent, dict):
            raise IntentPlanError("intent must be an object")
        intent_type = str(intent.get("intent") or intent.get("type") or "").strip().lower()
        if not intent_type:
            raise IntentPlanError("intent type is required")

        if intent_type not in {"move_to_entity", "move_to_position"}:
            actor_id = str(intent.get("actor_entity_id") or "").strip() or None
            region_id = None
            if actor_id:
                actor = self._entity(actor_id)
                region_id = str(actor.get("region_id") or "").strip() or None
            step = PlanStep(0, "semantic", deepcopy(intent), region_id, region_id)
            return IntentPlan(intent_type, actor_id, region_id, region_id, tuple([region_id] if region_id else []), (step,))

        actor_id = self._required(intent.get("actor_entity_id"), "actor_entity_id")
        actor = self._entity(actor_id)
        source_region = self._required(actor.get("region_id"), "actor.region_id")

        if intent_type == "move_to_entity":
            target_id = self._required(intent.get("target_entity_id"), "target_entity_id")
            target = self._entity(target_id)
            goal_region = self._required(target.get("region_id"), "target.region_id")
            final_intent = deepcopy(intent)
        else:
            goal_region = self._required(intent.get("region_id") or source_region, "region_id")
            final_intent = deepcopy(intent)

        route = self._path(source_region, goal_region)
        steps: list[PlanStep] = []
        previous_region = source_region
        for region_id in route[1:]:
            region = self._region(region_id)
            waypoint = {
                "intent": "move_to_position",
                "actor_entity_id": actor_id,
                "position": {"x": float(region.center[0]), "y": float(region.center[1])},
                "region_id": region_id,
            }
            steps.append(PlanStep(len(steps), "region_waypoint", waypoint, previous_region, region_id))
            previous_region = region_id

        steps.append(PlanStep(len(steps), "goal", final_intent, previous_region, goal_region))
        return IntentPlan(intent_type, actor_id, source_region, goal_region, route, tuple(steps))

    def revalidate_step(self, plan: IntentPlan, step_index: int) -> PlanStep:
        if step_index < 0 or step_index >= len(plan.steps):
            raise IntentPlanError("step index out of range")
        step = plan.steps[step_index]
        actor_id = plan.actor_entity_id
        if actor_id and step.expected_region_id:
            actor = self._entity(actor_id)
            actual = str(actor.get("region_id") or "").strip()
            if actual != step.expected_region_id:
                raise IntentPlanError(
                    f"plan stale at step {step_index}: actor region {actual!r} != expected {step.expected_region_id!r}"
                )
        return step
