from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcStrategyValue:
    """Deterministic expected-value overlay for learned NPC target rankings.

    Learning remains responsible for predicted satisfaction. This layer adds
    explainable travel and risk penalties without mutating learning evidence.
    Under-sampled targets remain in the exploration group; expected value only
    ranks alternatives within the same exploration/exploitation group.
    """

    def __init__(
        self,
        planner: Any,
        *,
        travel_weight: float = 0.12,
        risk_weight: float = 0.35,
        route_hops_scale: int = 8,
    ) -> None:
        self.planner = planner
        self.travel_weight = max(0.0, float(travel_weight))
        self.risk_weight = max(0.0, float(risk_weight))
        self.route_hops_scale = max(1, int(route_hops_scale))

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        store = getattr(self.planner, "store", None)
        getter = getattr(store, "get_entity", None)
        return getter(entity_id) if callable(getter) else None

    def _route_hops(self, actor: dict[str, Any], target: dict[str, Any]) -> int | None:
        source = str(actor.get("region_id") or "").strip()
        goal = str(target.get("region_id") or "").strip()
        regions = getattr(self.planner, "regions", None)
        route = getattr(regions, "route", None)
        if not source or not goal or not callable(route):
            return None
        path = route(source, goal)
        if not path:
            return None
        return max(0, len(path) - 1)

    def _risk(self, target: dict[str, Any], context: dict[str, Any] | None) -> float:
        raw_context = context if isinstance(context, dict) else {}
        try:
            context_risk = self._clamp(float(raw_context.get("danger_level", 0.0)))
        except (TypeError, ValueError):
            context_risk = 0.0
        props = target.get("properties") if isinstance(target.get("properties"), dict) else {}
        try:
            target_risk = self._clamp(float(props.get("risk_level", props.get("danger_level", 0.0))))
        except (TypeError, ValueError):
            target_risk = 0.0
        return max(context_risk, target_risk)

    def evaluate(
        self,
        *,
        actor_entity_id: str,
        rankings: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        actor = self._entity(actor_entity_id)
        if actor is None:
            return [deepcopy(row) for row in rankings]

        valued: list[dict[str, Any]] = []
        for raw in rankings:
            row = deepcopy(raw)
            target_id = str(row.get("target_entity_id") or "").strip()
            target = self._entity(target_id)
            hops = self._route_hops(actor, target) if target is not None else None
            travel_cost = 1.0 if hops is None else self._clamp(hops / self.route_hops_scale)
            risk = 1.0 if target is None else self._risk(target, context)
            predicted = self._clamp(float(row.get("effective_mean_satisfaction", row.get("mean_satisfaction", 0.0))))
            expected = predicted - self.travel_weight * travel_cost - self.risk_weight * risk
            row.update({
                "route_hops": hops,
                "travel_cost": travel_cost,
                "risk": risk,
                "predicted_satisfaction": predicted,
                "expected_value": expected,
                "travel_penalty": self.travel_weight * travel_cost,
                "risk_penalty": self.risk_weight * risk,
            })
            valued.append(row)

        valued.sort(key=lambda row: (
            0 if row.get("exploring") else 1,
            int(row.get("context_count", row.get("count", 0))) if row.get("exploring") else 0,
            -float(row.get("expected_value", 0.0)),
            str(row.get("target_entity_id") or ""),
        ))
        return valued

    def choose(self, *, actor_entity_id: str, rankings: list[dict[str, Any]], context: dict[str, Any] | None = None) -> tuple[str | None, list[dict[str, Any]]]:
        valued = self.evaluate(actor_entity_id=actor_entity_id, rankings=rankings, context=context)
        target = str(valued[0].get("target_entity_id") or "").strip() if valued else ""
        return (target or None), valued
