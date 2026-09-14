from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from .cold_store import FileRegionColdStore
from .regions import Region, RegionCatalog


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

    Region topology can be refreshed from the authoritative World State. This is
    required by persistent worlds whose map grows while the autonomous runtime is
    already running.
    """

    def __init__(self, store: FileRegionColdStore, regions: RegionCatalog) -> None:
        self.store = store
        self.regions = regions
        self.world_provider: Callable[[], dict[str, Any]] | None = None

    def set_world_provider(self, provider: Callable[[], dict[str, Any]] | None) -> None:
        self.world_provider = provider

    def _refresh_live_regions(self) -> None:
        provider = self.world_provider
        if provider is None:
            return
        world = provider()
        if isinstance(world, dict):
            self.refresh_regions(world)

    def refresh_regions(self, world: dict[str, Any]) -> None:
        raw_regions = world.get("regions")
        if not isinstance(raw_regions, list) or not raw_regions:
            return
        rows: list[Region] = []
        seen: set[str] = set()
        for raw in raw_regions:
            if not isinstance(raw, dict):
                continue
            region_id = str(raw.get("id") or "").strip()
            if not region_id or region_id in seen:
                continue
            center = raw.get("center") if isinstance(raw.get("center"), dict) else {}
            try:
                x = float(center.get("x", 0.0))
                y = float(center.get("y", 0.0))
                radius = float(raw.get("radius", 1.0))
            except (TypeError, ValueError):
                continue
            if radius <= 0:
                continue
            seen.add(region_id)
            rows.append(Region(
                id=region_id,
                center=(x, y),
                radius=radius,
                biome=str(raw.get("biome") or "unknown"),
                neighbors=tuple(sorted({str(v).strip() for v in raw.get("neighbors", []) if str(v).strip()})),
                metadata=dict(raw.get("metadata", {})) if isinstance(raw.get("metadata"), dict) else {},
            ))
        if rows:
            self.regions = RegionCatalog(rows)

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

    def _append_route_steps(
        self,
        *,
        steps: list[PlanStep],
        actor_id: str,
        source_region: str,
        target_entity_id: str,
        final_kind: str,
        base_intent: dict[str, Any],
    ) -> tuple[str, tuple[str, ...]]:
        target = self._entity(target_entity_id)
        goal_region = self._required(target.get("region_id"), "target.region_id")
        route = self._path(source_region, goal_region)
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
        goal_intent = deepcopy(base_intent)
        goal_intent["intent"] = "move_to_entity"
        goal_intent["actor_entity_id"] = actor_id
        goal_intent["target_entity_id"] = target_entity_id
        goal_intent.pop("via_entity_ids", None)
        steps.append(PlanStep(len(steps), final_kind, goal_intent, previous_region, goal_region))
        return goal_region, route

    def plan(self, intent: dict[str, Any]) -> IntentPlan:
        self._refresh_live_regions()
        if not isinstance(intent, dict):
            raise IntentPlanError("intent must be an object")
        intent_type = str(intent.get("intent") or intent.get("type") or "").strip().lower()
        if not intent_type:
            raise IntentPlanError("intent type is required")

        if intent_type == "move_via_entities":
            actor_id = self._required(intent.get("actor_entity_id"), "actor_entity_id")
            actor = self._entity(actor_id)
            source_region = self._required(actor.get("region_id"), "actor.region_id")
            via_raw = intent.get("via_entity_ids")
            if not isinstance(via_raw, list):
                raise IntentPlanError("via_entity_ids must be a list")
            via_ids = [str(value).strip() for value in via_raw if str(value).strip()]
            final_target = self._required(intent.get("target_entity_id"), "target_entity_id")
            targets = via_ids + [final_target]
            if not targets:
                raise IntentPlanError("compound movement requires at least one target")

            steps: list[PlanStep] = []
            region_path: list[str] = [source_region]
            current_region = source_region
            goal_region = source_region
            for index, target_id in enumerate(targets):
                goal_region, route = self._append_route_steps(
                    steps=steps,
                    actor_id=actor_id,
                    source_region=current_region,
                    target_entity_id=target_id,
                    final_kind="compound_goal" if index < len(targets) - 1 else "goal",
                    base_intent=intent,
                )
                for region_id in route[1:]:
                    if not region_path or region_path[-1] != region_id:
                        region_path.append(region_id)
                current_region = goal_region
            return IntentPlan(intent_type, actor_id, source_region, goal_region, tuple(region_path), tuple(steps))

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
        self._refresh_live_regions()
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
