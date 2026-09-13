from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcHorizonStrategy:
    """Overlay short-horizon competing-need pressure on composite strategies.

    The wrapped composite strategy remains responsible for candidate generation,
    empirical evidence, causal forecast and counterfactual simulation. This layer
    only reads those results and applies a bounded penalty when another need is
    projected to become urgent after the current strategy.
    """

    def __init__(
        self,
        base_strategy: Any,
        horizon_provider: Any,
        *,
        future_need_weight: float = 0.15,
    ) -> None:
        self.base_strategy = base_strategy
        self.horizon_provider = horizon_provider
        self.future_need_weight = min(1.0, max(0.0, float(future_need_weight)))

    def candidates(self, **kwargs: Any) -> list[dict[str, Any]]:
        fn = getattr(self.base_strategy, "candidates", None)
        if not callable(fn):
            return []
        rows = fn(**kwargs)
        return [deepcopy(row) for row in rows if isinstance(row, dict)]

    def rank(self, candidates: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        fn = getattr(self.base_strategy, "rank", None)
        if not callable(fn):
            return []
        base_rows = fn(candidates, **kwargs)
        need = str(kwargs.get("need") or "").strip().lower()
        assessor = getattr(self.horizon_provider, "assess", None)

        ranked: list[dict[str, Any]] = []
        for raw in base_rows:
            row = deepcopy(raw)
            horizon = None
            penalty = 0.0
            empirical = row.get("strategy_experience")
            empirical_ready = isinstance(empirical, dict) and bool(empirical.get("empirical_ready"))
            if callable(assessor) and need and not empirical_ready:
                try:
                    satisfaction = float(row.get("effective_satisfaction", row.get("predicted_satisfaction", 0.0)))
                except (TypeError, ValueError):
                    satisfaction = 0.0
                horizon = assessor(
                    current_need=need,
                    predicted_satisfaction=satisfaction,
                    counterfactual=row.get("counterfactual") if isinstance(row.get("counterfactual"), dict) else None,
                )
                if isinstance(horizon, dict):
                    try:
                        pressure = min(1.0, max(0.0, float(horizon.get("competing_need_pressure", 0.0))))
                    except (TypeError, ValueError):
                        pressure = 0.0
                    penalty = self.future_need_weight * pressure
                    row["expected_value"] = float(row.get("expected_value", 0.0)) - penalty
                    source = str(row.get("cost_source") or "heuristic")
                    if penalty > 0.0 and "horizon" not in source:
                        row["cost_source"] = source + "+horizon"

            row["need_horizon"] = deepcopy(horizon)
            row["future_need_penalty"] = penalty
            ranked.append(row)

        ranked.sort(key=lambda row: (-float(row.get("expected_value", 0.0)), str(row.get("strategy_id") or "")))
        return ranked

    def choose(self, candidates: list[dict[str, Any]], **kwargs: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        ranked = self.rank(candidates, **kwargs)
        return (deepcopy(ranked[0]) if ranked else None), ranked
