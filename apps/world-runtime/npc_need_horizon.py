from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcNeedHorizon:
    """Assess short-horizon conflicts between internal needs.

    This layer never mutates persistent need state. It consumes a counterfactual
    trajectory and applies one explicitly conditional planning assumption:
    *if the current strategy succeeds*, the current need may be reduced by the
    predicted terminal satisfaction. That assumed reduction exists only inside
    this assessment and is never written to memory, learning, or world state.
    """

    PRIORITIES = {
        "safety": 1000,
        "energy": 700,
        "social": 400,
        "curiosity": 200,
    }

    def __init__(
        self,
        *,
        urgency_threshold: float = 0.70,
        defer_margin: float = 0.10,
        max_horizon_needs: int = 2,
    ) -> None:
        self.urgency_threshold = min(1.0, max(0.0, float(urgency_threshold)))
        self.defer_margin = max(0.0, float(defer_margin))
        self.max_horizon_needs = max(1, int(max_horizon_needs))

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    @classmethod
    def _utility(cls, need: str, severity: float) -> float:
        return cls._clamp(severity) * float(cls.PRIORITIES.get(need, 0))

    def assess(
        self,
        *,
        current_need: str,
        predicted_satisfaction: float,
        counterfactual: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(counterfactual, dict):
            return None
        current_need = str(current_need or "").strip().lower()
        if current_need not in self.PRIORITIES:
            return None
        raw_end = counterfactual.get("end_needs")
        if not isinstance(raw_end, dict):
            return None

        end_needs = {
            name: self._clamp(float(raw_end.get(name, 0.0) or 0.0))
            for name in self.PRIORITIES
        }
        assumed = dict(end_needs)
        satisfaction = self._clamp(predicted_satisfaction)
        assumed[current_need] = self._clamp(assumed[current_need] - satisfaction)

        ranked = [
            {
                "need": name,
                "severity": severity,
                "priority": self.PRIORITIES[name],
                "utility": self._utility(name, severity),
                "urgent": severity >= self.urgency_threshold,
            }
            for name, severity in assumed.items()
        ]
        ranked.sort(key=lambda row: (-float(row["utility"]), -int(row["priority"]), str(row["need"])))

        current_row = next(row for row in ranked if row["need"] == current_need)
        competing = [row for row in ranked if row["need"] != current_need and row["urgent"]]
        next_row = competing[0] if competing else None

        defer_to_need = None
        if next_row is not None:
            if float(next_row["utility"]) > float(current_row["utility"]) + self.defer_margin * 1000.0:
                defer_to_need = str(next_row["need"])

        sequence = [current_need]
        if next_row is not None and len(sequence) < self.max_horizon_needs:
            sequence.append(str(next_row["need"]))

        normalized_competing_pressure = 0.0
        if next_row is not None:
            normalized_competing_pressure = min(1.0, float(next_row["utility"]) / 1000.0)

        return {
            "horizon_schema": "npc_need_horizon_v1",
            "current_need": current_need,
            "predicted_terminal_satisfaction": satisfaction,
            "counterfactual_end_needs": deepcopy(end_needs),
            "conditional_post_outcome_needs": deepcopy(assumed),
            "ranked_future_needs": deepcopy(ranked),
            "next_urgent_need": str(next_row["need"]) if next_row is not None else None,
            "next_urgent_utility": float(next_row["utility"]) if next_row is not None else 0.0,
            "defer_to_need": defer_to_need,
            "recommended_need_sequence": sequence,
            "competing_need_pressure": normalized_competing_pressure,
            "assumption": "current strategy succeeds with predicted terminal satisfaction",
            "mutates_state": False,
        }
