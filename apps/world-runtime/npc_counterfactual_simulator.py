from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcCounterfactualSimulator:
    """Project a bounded strategy into a read-only shadow trajectory.

    This is not authoritative simulation: no world state is cloned or mutated.
    The simulator advances only compact variables relevant to strategy comparison
    (logical tick, period transition exposure and risk) and returns an explainable
    trace that can be audited alongside the chosen strategy.
    """

    def __init__(self, causal_forecast_provider: Any | None = None, *, max_steps: int = 16) -> None:
        self.causal_forecast_provider = causal_forecast_provider
        self.max_steps = max(1, int(max_steps))

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    @staticmethod
    def _phase_ticks(phase: dict[str, Any]) -> int:
        kind = str(phase.get("kind") or "")
        if kind == "wait_ticks":
            try:
                return max(0, int(phase.get("ticks", 0)))
            except (TypeError, ValueError):
                return 0
        if kind == "move_to_entity":
            try:
                return max(1, int(phase.get("estimated_ticks", 1)))
            except (TypeError, ValueError):
                return 1
        return 1

    @staticmethod
    def _protection(strategy_id: str, phase_index: int) -> float:
        strategy_id = str(strategy_id or "")
        if strategy_id.startswith("via_shelter:") and phase_index == 0:
            return 0.50
        if strategy_id.startswith("via_shelter:"):
            return 0.25
        if strategy_id == "wait_then_direct" and phase_index == 0:
            return 0.20
        return 0.0

    def simulate(
        self,
        *,
        strategy: dict[str, Any],
        context: dict[str, Any] | None,
        fallback_estimated_ticks: int = 0,
    ) -> dict[str, Any]:
        ctx = deepcopy(context or {})
        try:
            tick = int(ctx.get("logical_tick", 0))
        except (TypeError, ValueError):
            tick = 0
        try:
            risk = self._clamp(float(ctx.get("danger_level", 0.0)))
        except (TypeError, ValueError):
            risk = 0.0
        period = str(ctx.get("period") or "unknown")
        strategy_id = str(strategy.get("strategy_id") or "direct")
        phases = [deepcopy(p) for p in strategy.get("phases", []) if isinstance(p, dict)]
        if not phases:
            phases = [{"kind": "estimated", "estimated_ticks": max(0, int(fallback_estimated_ticks))}]

        trace: list[dict[str, Any]] = []
        total_ticks = 0
        peak_risk = risk
        cumulative_risk = 0.0
        observed_steps = 0

        for phase_index, phase in enumerate(phases[: self.max_steps]):
            duration = self._phase_ticks(phase)
            if phase.get("kind") == "estimated":
                duration = max(0, int(phase.get("estimated_ticks", fallback_estimated_ticks)))
            protection = self._protection(strategy_id, phase_index)
            phase_start = tick + total_ticks
            phase_end = phase_start + duration

            forecast = None
            assessor = getattr(self.causal_forecast_provider, "assess", None)
            if callable(assessor):
                fctx = deepcopy(ctx)
                fctx["logical_tick"] = phase_start
                fctx["period"] = period
                fctx["danger_level"] = risk
                value = assessor(context=fctx, estimated_ticks=duration)
                forecast = deepcopy(value) if isinstance(value, dict) else None

            projected_risk = risk
            next_period = period
            if forecast is not None:
                projected_risk = self._clamp(float(forecast.get("projected_danger", risk)))
                next_period = str(forecast.get("to_period") or period)

            effective_risk = self._clamp(projected_risk * (1.0 - protection))
            peak_risk = max(peak_risk, effective_risk)
            cumulative_risk += effective_risk * max(1, duration)
            observed_steps += max(1, duration)
            trace.append({
                "phase_index": phase_index,
                "kind": str(phase.get("kind") or "unknown"),
                "start_tick": phase_start,
                "end_tick": phase_end,
                "period_before": period,
                "period_after": next_period,
                "risk_before": risk,
                "projected_risk": projected_risk,
                "protection": protection,
                "effective_risk": effective_risk,
                "causal_forecast": forecast,
            })
            total_ticks += duration
            risk = projected_risk
            period = next_period

        mean_risk = self._clamp(cumulative_risk / max(1, observed_steps))
        return {
            "counterfactual_schema": "npc_counterfactual_v1",
            "strategy_id": strategy_id,
            "start_tick": tick,
            "end_tick": tick + total_ticks,
            "estimated_ticks": total_ticks,
            "start_period": str(ctx.get("period") or "unknown"),
            "end_period": period,
            "start_risk": self._clamp(float(ctx.get("danger_level", 0.0) or 0.0)),
            "mean_effective_risk": mean_risk,
            "peak_effective_risk": self._clamp(peak_risk),
            "trace": trace,
            "mutates_world": False,
        }
