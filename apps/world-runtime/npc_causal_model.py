from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcCausalModel:
    """Track provisional causal hypotheses from repeated world transitions.

    The model never asserts causality as fact. It records temporal candidate-cause
    transitions, observed effects, support/counterevidence and confidence. The
    first baseline focuses on environment period transitions and danger changes.
    """

    def __init__(self, path: Path, *, prior_strength: float = 4.0, evidence_limit: int = 16, world_provider: Any | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prior_strength = max(0.1, float(prior_strength))
        self.evidence_limit = max(1, int(evidence_limit))
        self.world_provider = world_provider

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"causal_schema": "npc_causal_hypotheses_v1", "entries": {}, "processed_observation_ids": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        value.setdefault("causal_schema", "npc_causal_hypotheses_v1")
        value.setdefault("entries", {})
        value.setdefault("processed_observation_ids", [])
        return value

    def _save(self, state: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _environment(world: dict[str, Any] | None) -> dict[str, Any]:
        world = world if isinstance(world, dict) else {}
        env = world.get("environment") if isinstance(world.get("environment"), dict) else {}
        try:
            danger = min(1.0, max(0.0, float(env.get("danger_level", 0.0))))
        except (TypeError, ValueError):
            danger = 0.0
        return {
            "period": str(env.get("period") or "unknown"),
            "weather": str(env.get("weather") or env.get("weather_state") or "unknown"),
            "danger_level": danger,
        }

    def snapshot(self) -> dict[str, Any]:
        provider = self.world_provider
        value = provider() if callable(provider) else {}
        return self._environment(value if isinstance(value, dict) else {})

    @staticmethod
    def _effect_direction(delta: float, *, epsilon: float = 1e-9) -> str:
        if delta > epsilon:
            return "increase"
        if delta < -epsilon:
            return "decrease"
        return "stable"

    @staticmethod
    def _key(cause: dict[str, Any], effect: dict[str, Any]) -> str:
        return "|".join((
            str(cause.get("kind") or ""),
            str(cause.get("from") or ""),
            str(cause.get("to") or ""),
            str(effect.get("metric") or ""),
            str(effect.get("expected_direction") or ""),
        ))

    def observe_environment_transition(
        self,
        *,
        observation_id: str,
        logical_tick: int,
        before: dict[str, Any],
        after: dict[str, Any],
        source_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        observation_id = str(observation_id or "").strip()
        if not observation_id:
            raise ValueError("observation_id is required")
        before_env = self._environment({"environment": before})
        after_env = self._environment({"environment": after})
        if before_env["period"] == after_env["period"]:
            return None

        cause = {
            "kind": "environment_period_transition",
            "from": before_env["period"],
            "to": after_env["period"],
            "weather": after_env["weather"],
        }
        delta = float(after_env["danger_level"]) - float(before_env["danger_level"])
        observed_direction = self._effect_direction(delta)
        expected_direction = "increase" if after_env["period"] == "night" else "decrease" if after_env["period"] == "day" else observed_direction
        effect = {
            "metric": "environment.danger_level",
            "expected_direction": expected_direction,
        }

        state = self._load()
        processed = {str(value) for value in state.get("processed_observation_ids", [])}
        key = self._key(cause, effect)
        entries = state.setdefault("entries", {})
        if observation_id in processed:
            row = entries.get(key)
            return deepcopy(row) if isinstance(row, dict) else None

        row = entries.get(key)
        if not isinstance(row, dict):
            row = {
                "causal_hypothesis_schema": "npc_causal_hypothesis_v1",
                "hypothesis_type": "temporal_environment_relation",
                "cause": deepcopy(cause),
                "effect": deepcopy(effect),
                "count": 0,
                "support_count": 0,
                "counter_count": 0,
                "neutral_count": 0,
                "mean_effect_delta": 0.0,
                "confidence": 0.0,
                "evidence": [],
                "status": "provisional",
            }

        count = max(0, int(row.get("count", 0))) + 1
        old_mean = float(row.get("mean_effect_delta", 0.0))
        row["mean_effect_delta"] = old_mean + (delta - old_mean) / count
        row["count"] = count
        if observed_direction == expected_direction:
            row["support_count"] = int(row.get("support_count", 0)) + 1
        elif observed_direction == "stable":
            row["neutral_count"] = int(row.get("neutral_count", 0)) + 1
        else:
            row["counter_count"] = int(row.get("counter_count", 0)) + 1

        directional_balance = abs(int(row.get("support_count", 0)) - int(row.get("counter_count", 0))) / max(1, count)
        evidence_strength = count / (count + self.prior_strength)
        row["confidence"] = evidence_strength * directional_balance
        row["last_observation_id"] = observation_id
        row["last_logical_tick"] = int(logical_tick)
        evidence = [item for item in row.get("evidence", []) if isinstance(item, dict)]
        evidence.append({
            "observation_id": observation_id,
            "logical_tick": int(logical_tick),
            "before": deepcopy(before_env),
            "after": deepcopy(after_env),
            "observed_direction": observed_direction,
            "delta": delta,
            "source_events": deepcopy(source_events or []),
        })
        row["evidence"] = evidence[-self.evidence_limit :]
        entries[key] = row
        processed.add(observation_id)
        state["processed_observation_ids"] = sorted(processed)
        self._save(state)
        return deepcopy(row)

    def hypothesis(
        self,
        *,
        from_period: str,
        to_period: str,
        expected_direction: str,
    ) -> dict[str, Any] | None:
        cause = {"kind": "environment_period_transition", "from": str(from_period), "to": str(to_period)}
        effect = {"metric": "environment.danger_level", "expected_direction": str(expected_direction)}
        row = self._load().get("entries", {}).get(self._key(cause, effect))
        return deepcopy(row) if isinstance(row, dict) else None

    def hypotheses(self) -> list[dict[str, Any]]:
        rows = [deepcopy(row) for row in self._load().get("entries", {}).values() if isinstance(row, dict)]
        rows.sort(key=lambda row: (
            str((row.get("cause") or {}).get("from") or ""),
            str((row.get("cause") or {}).get("to") or ""),
            str((row.get("effect") or {}).get("expected_direction") or ""),
        ))
        return rows
