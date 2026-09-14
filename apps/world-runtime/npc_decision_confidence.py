from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcDecisionConfidence:
    """Estimate bounded confidence for one already-ranked NPC strategy.

    Confidence is descriptive metadata only. It never changes ranking, threshold,
    proposal approval or mutation authority. Empirical strategy evidence is the
    strongest source; otherwise causal forecast and counterfactual support add
    bounded confidence above a low heuristic baseline.
    """

    def __init__(self, *, heuristic_baseline: float = 0.20) -> None:
        self.heuristic_baseline = self._clamp(heuristic_baseline)

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    def assess(self, row: dict[str, Any]) -> dict[str, Any]:
        strategy = deepcopy(row if isinstance(row, dict) else {})
        empirical = strategy.get("strategy_experience") if isinstance(strategy.get("strategy_experience"), dict) else None
        forecast = strategy.get("causal_forecast") if isinstance(strategy.get("causal_forecast"), dict) else None
        counterfactual = strategy.get("counterfactual") if isinstance(strategy.get("counterfactual"), dict) else None
        horizon = strategy.get("need_horizon") if isinstance(strategy.get("need_horizon"), dict) else None

        sources: list[dict[str, Any]] = []
        if empirical and bool(empirical.get("empirical_ready")):
            try:
                count = max(0, int(empirical.get("count", 0)))
            except (TypeError, ValueError):
                count = 0
            score = self._clamp(0.75 + min(0.20, count * 0.025))
            sources.append({"source": "empirical_strategy", "weight": score, "count": count})
            level = "high" if score >= 0.75 else "medium"
            return {
                "decision_confidence_schema": "npc_decision_confidence_v1",
                "score": score,
                "level": level,
                "sources": sources,
                "empirical_dominant": True,
                "mutates_state": False,
            }

        score = self.heuristic_baseline
        sources.append({"source": "heuristic", "weight": self.heuristic_baseline})

        if counterfactual is not None:
            contribution = 0.20
            score += contribution
            sources.append({"source": "counterfactual", "weight": contribution})

        if forecast is not None:
            try:
                causal_confidence = self._clamp(float(forecast.get("confidence", 0.0)))
            except (TypeError, ValueError):
                causal_confidence = 0.0
            contribution = 0.25 * causal_confidence
            score += contribution
            sources.append({"source": "causal_forecast", "weight": contribution, "confidence": causal_confidence})

        if horizon is not None:
            try:
                pressure = self._clamp(float(horizon.get("competing_need_pressure", 0.0)))
            except (TypeError, ValueError):
                pressure = 0.0
            # Horizon is a second-order projection. It adds only a small amount of
            # support, proportional to how explicit the competing pressure is.
            contribution = 0.10 * pressure
            score += contribution
            sources.append({"source": "need_horizon", "weight": contribution, "pressure": pressure})

        score = self._clamp(score)
        level = "high" if score >= 0.75 else "medium" if score >= 0.45 else "low"
        return {
            "decision_confidence_schema": "npc_decision_confidence_v1",
            "score": score,
            "level": level,
            "sources": sources,
            "empirical_dominant": False,
            "mutates_state": False,
        }
