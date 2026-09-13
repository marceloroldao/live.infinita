from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcCausalForecast:
    """Bounded forecast from provisional causal hypotheses plus logical schedules.

    A forecast is not a fact and never mutates the world. It is available only
    when a scheduled period transition is expected to occur during a candidate
    strategy and a matching causal hypothesis has enough confidence.

    The forecast reads the append-only world-event schedule ledger directly. This
    keeps cognition independent from the live scheduler process while preserving
    the same persisted source of truth.
    """

    def __init__(
        self,
        causal_model: Any,
        schedule_path: Path,
        *,
        min_confidence: float = 0.15,
        max_blend: float = 0.35,
    ) -> None:
        self.causal_model = causal_model
        self.schedule_path = Path(schedule_path)
        self.min_confidence = min(1.0, max(0.0, float(min_confidence)))
        self.max_blend = min(1.0, max(0.0, float(max_blend)))

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    @staticmethod
    def _period_from_operations(operations: list[dict[str, Any]]) -> str | None:
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("op") != "set_world":
                continue
            path = operation.get("path")
            if path == ["environment", "period"]:
                value = str(operation.get("value") or "").strip()
                return value or None
        return None

    def _current_schedule(self) -> list[dict[str, Any]]:
        if not self.schedule_path.exists():
            return []
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        with self.schedule_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                event_id = str(row.get("scheduled_event_id") or "").strip()
                if not event_id:
                    continue
                if event_id not in latest:
                    order.append(event_id)
                latest[event_id] = row
        return [latest[event_id] for event_id in order]

    def next_period_transition(self, *, logical_tick: int, current_period: str) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for row in self._current_schedule():
            if row.get("status") != "scheduled":
                continue
            try:
                due_tick = int(row.get("due_tick", -1))
            except (TypeError, ValueError):
                continue
            if due_tick < int(logical_tick):
                continue
            period = self._period_from_operations(list(row.get("operations") or []))
            if not period or period == current_period:
                continue
            candidates.append({
                "due_tick": due_tick,
                "to_period": period,
                "scheduled_event_id": row.get("scheduled_event_id"),
                "metadata": deepcopy(row.get("metadata") or {}),
            })
        if not candidates:
            return None
        candidates.sort(key=lambda row: (int(row["due_tick"]), str(row.get("scheduled_event_id") or "")))
        chosen = candidates[0]
        chosen["ticks_until"] = max(0, int(chosen["due_tick"]) - int(logical_tick))
        return chosen

    def assess(
        self,
        *,
        context: dict[str, Any] | None,
        estimated_ticks: int,
    ) -> dict[str, Any] | None:
        context = context if isinstance(context, dict) else {}
        try:
            logical_tick = int(context.get("logical_tick"))
        except (TypeError, ValueError):
            return None
        current_period = str(context.get("period") or "").strip()
        if not current_period:
            return None
        try:
            current_danger = self._clamp(float(context.get("danger_level", 0.0)))
        except (TypeError, ValueError):
            current_danger = 0.0

        transition = self.next_period_transition(logical_tick=logical_tick, current_period=current_period)
        if transition is None or int(transition["ticks_until"]) > max(0, int(estimated_ticks)):
            return None

        to_period = str(transition["to_period"])
        expected_direction = "increase" if to_period == "night" else "decrease" if to_period == "day" else "stable"
        getter = getattr(self.causal_model, "hypothesis", None)
        if not callable(getter):
            return None
        hypothesis = getter(
            from_period=current_period,
            to_period=to_period,
            expected_direction=expected_direction,
        )
        if not isinstance(hypothesis, dict):
            return None
        try:
            confidence = self._clamp(float(hypothesis.get("confidence", 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < self.min_confidence:
            return None
        try:
            mean_delta = float(hypothesis.get("mean_effect_delta", 0.0))
        except (TypeError, ValueError):
            mean_delta = 0.0

        blend = min(self.max_blend, confidence * self.max_blend)
        projected_danger = self._clamp(current_danger + mean_delta * confidence)
        return {
            "forecast_schema": "npc_causal_forecast_v1",
            "from_period": current_period,
            "to_period": to_period,
            "logical_tick": logical_tick,
            "due_tick": int(transition["due_tick"]),
            "ticks_until": int(transition["ticks_until"]),
            "estimated_ticks": max(0, int(estimated_ticks)),
            "current_danger": current_danger,
            "projected_danger": projected_danger,
            "mean_effect_delta": mean_delta,
            "confidence": confidence,
            "blend": blend,
            "hypothesis": deepcopy(hypothesis),
            "scheduled_event_id": transition.get("scheduled_event_id"),
        }
