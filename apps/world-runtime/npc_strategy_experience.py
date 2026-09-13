from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcStrategyExperience:
    """Learn empirical execution cost for need-driven strategies.

    Evidence is keyed by NPC + need + target + canonical decision context. It
    stores online means for elapsed logical ticks, preemptions, replans and
    observed risk. No randomness and O(1) update per completed outcome.
    """

    def __init__(self, path: Path, *, min_samples: int = 2) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.min_samples = max(1, int(min_samples))
        self._state = self._load()

    @staticmethod
    def canonical_context(context: dict[str, Any] | None) -> dict[str, Any]:
        raw = context if isinstance(context, dict) else {}
        try:
            danger = min(1.0, max(0.0, float(raw.get("danger_level", 0.0))))
        except (TypeError, ValueError):
            danger = 0.0
        return {
            "period": str(raw.get("period") or "unknown").strip().lower() or "unknown",
            "weather": str(raw.get("weather") or "unknown").strip().lower() or "unknown",
            "region_id": str(raw.get("region_id") or "unknown").strip() or "unknown",
            "danger_band": "high" if danger >= 0.67 else "medium" if danger >= 0.34 else "low",
        }

    @classmethod
    def _key(cls, npc_id: str, need: str, target_id: str, context: dict[str, Any] | None) -> str:
        ctx = json.dumps(cls.canonical_context(context), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{npc_id}\u001f{need}\u001f{ctx}\u001f{target_id}"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "npc_strategy_experience_v1", "entries": {}, "outcomes": {}}
        with self.path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        if not isinstance(value, dict):
            raise ValueError("invalid strategy experience state")
        value.setdefault("schema", "npc_strategy_experience_v1")
        value.setdefault("entries", {})
        value.setdefault("outcomes", {})
        return value

    def _save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._state, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        tmp.replace(self.path)

    @staticmethod
    def _mean(old: float, count: int, value: float) -> float:
        return old + (value - old) / (count + 1)

    def observe(
        self,
        *,
        outcome_id: str,
        npc_id: str,
        need: str,
        target_entity_id: str,
        context: dict[str, Any] | None,
        elapsed_ticks: int,
        preemptions: int,
        replans: int,
        observed_risk: float,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        outcome_id = str(outcome_id or "").strip()
        if not outcome_id:
            raise ValueError("outcome_id is required")
        outcomes = self._state.setdefault("outcomes", {})
        if outcome_id in outcomes:
            return deepcopy(outcomes[outcome_id])

        npc_id = str(npc_id or "").strip()
        need = str(need or "").strip().lower()
        target_entity_id = str(target_entity_id or "").strip()
        if not npc_id or not need or not target_entity_id:
            raise ValueError("npc_id, need and target_entity_id are required")

        elapsed = max(0, int(elapsed_ticks))
        pre = max(0, int(preemptions))
        rep = max(0, int(replans))
        risk = min(1.0, max(0.0, float(observed_risk)))
        key = self._key(npc_id, need, target_entity_id, context)
        entries = self._state.setdefault("entries", {})
        current = entries.get(key) if isinstance(entries.get(key), dict) else {}
        count = int(current.get("count", 0))
        row = {
            "npc_id": npc_id,
            "need": need,
            "target_entity_id": target_entity_id,
            "context": self.canonical_context(context),
            "count": count + 1,
            "mean_elapsed_ticks": self._mean(float(current.get("mean_elapsed_ticks", 0.0)), count, float(elapsed)),
            "mean_preemptions": self._mean(float(current.get("mean_preemptions", 0.0)), count, float(pre)),
            "mean_replans": self._mean(float(current.get("mean_replans", 0.0)), count, float(rep)),
            "mean_observed_risk": self._mean(float(current.get("mean_observed_risk", 0.0)), count, risk),
            "last_outcome_id": outcome_id,
            "last_plan_id": str(plan_id or "").strip() or None,
        }
        entries[key] = row
        result = {
            "outcome_id": outcome_id,
            **deepcopy(row),
            "empirical_ready": row["count"] >= self.min_samples,
        }
        outcomes[outcome_id] = result
        self._save()
        return deepcopy(result)

    def stats(self, npc_id: str, need: str, target_entity_id: str, context: dict[str, Any] | None) -> dict[str, Any] | None:
        row = self._state.get("entries", {}).get(self._key(str(npc_id), str(need).lower(), str(target_entity_id), context))
        if not isinstance(row, dict):
            return None
        result = deepcopy(row)
        result["empirical_ready"] = int(result.get("count", 0)) >= self.min_samples
        return result

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)
