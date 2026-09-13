from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcCompositeStrategy:
    """Generate and rank deterministic multi-phase strategies for one need target.

    This component does not mutate world state and does not schedule plans. It only
    emits explainable strategy candidates that a later compiler can turn into
    semantic plan phases. When enough full-strategy experience exists, ranking may
    use that empirical evidence instead of route heuristics. Before empirical
    evidence is mature, a bounded provisional causal forecast may adjust heuristic
    risk when a scheduled world transition is likely to happen during execution.
    """

    def __init__(
        self,
        planner: Any,
        *,
        wait_penalty_per_tick: float = 0.02,
        strategy_experience_provider: Any | None = None,
        causal_forecast_provider: Any | None = None,
    ) -> None:
        self.planner = planner
        self.wait_penalty_per_tick = max(0.0, float(wait_penalty_per_tick))
        self.strategy_experience_provider = strategy_experience_provider
        self.causal_forecast_provider = causal_forecast_provider

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        store = getattr(self.planner, "store", None)
        getter = getattr(store, "get_entity", None)
        return getter(entity_id) if callable(getter) else None

    def _hops(self, source_region: str, goal_region: str) -> int | None:
        regions = getattr(self.planner, "regions", None)
        route = getattr(regions, "route", None)
        if not source_region or not goal_region or not callable(route):
            return None
        path = route(source_region, goal_region)
        return max(0, len(path) - 1) if path else None

    @staticmethod
    def _risk(entity: dict[str, Any] | None) -> float:
        if not isinstance(entity, dict):
            return 1.0
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        try:
            value = float(props.get("risk_level", props.get("danger_level", 0.0)))
        except (TypeError, ValueError):
            value = 0.0
        return min(1.0, max(0.0, value))

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    @staticmethod
    def _forecast_exposure(strategy_id: str) -> float:
        strategy_id = str(strategy_id or "")
        if strategy_id.startswith("via_shelter:"):
            return 0.50
        if strategy_id == "wait_then_direct":
            return 0.80
        return 1.0

    def candidates(
        self,
        *,
        actor_entity_id: str,
        target_entity_id: str,
        predicted_satisfaction: float,
        context: dict[str, Any] | None = None,
        shelter_entity_ids: list[str] | None = None,
        wait_ticks: int = 3,
    ) -> list[dict[str, Any]]:
        actor = self._entity(actor_entity_id)
        target = self._entity(target_entity_id)
        if actor is None or target is None:
            return []
        source_region = str(actor.get("region_id") or "")
        target_region = str(target.get("region_id") or "")
        direct_hops = self._hops(source_region, target_region)
        predicted = min(1.0, max(0.0, float(predicted_satisfaction)))
        raw_context = context if isinstance(context, dict) else {}
        try:
            context_risk = min(1.0, max(0.0, float(raw_context.get("danger_level", 0.0))))
        except (TypeError, ValueError):
            context_risk = 0.0

        rows: list[dict[str, Any]] = [{
            "strategy_id": "direct",
            "phases": [{"kind": "move_to_entity", "target_entity_id": target_entity_id}],
            "estimated_hops": direct_hops,
            "estimated_risk": max(context_risk, self._risk(target)),
            "wait_ticks": 0,
            "predicted_satisfaction": predicted,
        }]

        for shelter_id in sorted({str(v).strip() for v in shelter_entity_ids or [] if str(v).strip()}):
            shelter = self._entity(shelter_id)
            if shelter is None:
                continue
            shelter_region = str(shelter.get("region_id") or "")
            a = self._hops(source_region, shelter_region)
            b = self._hops(shelter_region, target_region)
            if a is None or b is None:
                continue
            rows.append({
                "strategy_id": f"via_shelter:{shelter_id}",
                "phases": [
                    {"kind": "move_to_entity", "target_entity_id": shelter_id},
                    {"kind": "move_to_entity", "target_entity_id": target_entity_id},
                ],
                "estimated_hops": a + b,
                "estimated_risk": max(self._risk(shelter), self._risk(target)),
                "wait_ticks": 0,
                "predicted_satisfaction": predicted,
            })

        waits = max(0, int(wait_ticks))
        if waits:
            rows.append({
                "strategy_id": "wait_then_direct",
                "phases": [
                    {"kind": "wait_ticks", "ticks": waits},
                    {"kind": "move_to_entity", "target_entity_id": target_entity_id},
                ],
                "estimated_hops": direct_hops,
                "estimated_risk": max(self._risk(target), context_risk * 0.5),
                "wait_ticks": waits,
                "predicted_satisfaction": predicted,
            })
        return rows

    def _empirical_stats(
        self,
        *,
        actor_entity_id: str | None,
        need: str | None,
        target_entity_id: str | None,
        strategy_id: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        provider = self.strategy_experience_provider
        getter = getattr(provider, "strategy_stats", None) if provider is not None else None
        if not callable(getter) or not actor_entity_id or not need or not target_entity_id:
            return None
        value = getter(actor_entity_id, need, target_entity_id, strategy_id, context)
        return value if isinstance(value, dict) else None

    def _causal_forecast(self, *, context: dict[str, Any] | None, estimated_ticks: int) -> dict[str, Any] | None:
        provider = self.causal_forecast_provider
        assessor = getattr(provider, "assess", None) if provider is not None else None
        if not callable(assessor):
            return None
        value = assessor(context=context, estimated_ticks=estimated_ticks)
        return deepcopy(value) if isinstance(value, dict) else None

    def rank(
        self,
        candidates: list[dict[str, Any]],
        *,
        travel_weight: float = 0.12,
        risk_weight: float = 0.35,
        route_hops_scale: int = 8,
        actor_entity_id: str | None = None,
        need: str | None = None,
        target_entity_id: str | None = None,
        context: dict[str, Any] | None = None,
        elapsed_ticks_scale: int = 12,
        interruption_weight: float = 0.03,
    ) -> list[dict[str, Any]]:
        scale = max(1, int(route_hops_scale))
        elapsed_scale = max(1, int(elapsed_ticks_scale))
        ranked: list[dict[str, Any]] = []
        for raw in candidates:
            row = deepcopy(raw)
            hops = row.get("estimated_hops")
            travel_cost = 1.0 if hops is None else min(1.0, max(0.0, float(hops) / scale))
            risk = self._clamp(float(row.get("estimated_risk", 0.0)))
            wait_ticks = max(0, int(row.get("wait_ticks", 0)))
            wait_penalty = wait_ticks * self.wait_penalty_per_tick
            predicted = self._clamp(float(row.get("predicted_satisfaction", 0.0)))
            strategy_id = str(row.get("strategy_id") or "")
            expected = predicted - float(travel_weight) * travel_cost - float(risk_weight) * risk - wait_penalty
            source = "heuristic"
            empirical = self._empirical_stats(
                actor_entity_id=actor_entity_id,
                need=need,
                target_entity_id=target_entity_id,
                strategy_id=strategy_id,
                context=context,
            )
            forecast = None
            forecast_exposure = 0.0
            if empirical and bool(empirical.get("empirical_ready")):
                satisfaction = self._clamp(float(empirical.get("mean_satisfaction", predicted)))
                elapsed_cost = self._clamp(float(empirical.get("mean_elapsed_ticks", 0.0)) / elapsed_scale)
                empirical_risk = self._clamp(float(empirical.get("mean_observed_risk", risk)))
                interruptions = max(0.0, float(empirical.get("mean_preemptions", 0.0))) + max(
                    0.0, float(empirical.get("mean_replans", 0.0))
                )
                expected = (
                    satisfaction
                    - float(travel_weight) * elapsed_cost
                    - float(risk_weight) * empirical_risk
                    - float(interruption_weight) * interruptions
                )
                travel_cost = elapsed_cost
                risk = empirical_risk
                predicted = satisfaction
                source = "empirical"
            else:
                estimated_ticks = max(0, int(hops or 0)) + wait_ticks
                forecast = self._causal_forecast(context=context, estimated_ticks=estimated_ticks)
                if forecast is not None:
                    current_danger = self._clamp(float(forecast.get("current_danger", risk)))
                    projected_danger = self._clamp(float(forecast.get("projected_danger", current_danger)))
                    blend = self._clamp(float(forecast.get("blend", 0.0)))
                    forecast_exposure = self._forecast_exposure(strategy_id)
                    delta = projected_danger - current_danger
                    risk = self._clamp(risk + delta * blend * forecast_exposure)
                    expected = predicted - float(travel_weight) * travel_cost - float(risk_weight) * risk - wait_penalty
                    if blend > 0.0:
                        source = "heuristic+causal_forecast"

            row.update({
                "travel_cost": travel_cost,
                "wait_penalty": wait_penalty,
                "expected_value": expected,
                "cost_source": source,
                "effective_satisfaction": predicted,
                "effective_risk": risk,
                "strategy_experience": deepcopy(empirical),
                "causal_forecast": deepcopy(forecast),
                "causal_forecast_exposure": forecast_exposure,
            })
            ranked.append(row)
        ranked.sort(key=lambda row: (-float(row.get("expected_value", 0.0)), str(row.get("strategy_id") or "")))
        return ranked

    def choose(self, candidates: list[dict[str, Any]], **kwargs: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        ranked = self.rank(candidates, **kwargs)
        return (deepcopy(ranked[0]) if ranked else None), ranked
