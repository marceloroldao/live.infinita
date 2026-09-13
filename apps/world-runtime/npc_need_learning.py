from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcNeedLearning:
    """Deterministic incremental outcome learning for need-driven targets.

    Maintains both global evidence per (npc, need, target) and contextual evidence
    per (npc, need, context, target). Context is canonicalized and selection falls
    back to global evidence while contextual evidence is sparse. No randomness.
    """

    def __init__(self, path: Path, *, exploration_samples: int = 2, contextual_min_samples: int = 2) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.exploration_samples = max(0, int(exploration_samples))
        self.contextual_min_samples = max(1, int(contextual_min_samples))
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "npc_need_learning_v2", "entries": {}, "context_entries": {}, "outcomes": {}}
        with self.path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        if not isinstance(value, dict):
            raise ValueError("invalid NPC need learning state")
        value["schema"] = "npc_need_learning_v2"
        value.setdefault("entries", {})
        value.setdefault("context_entries", {})
        value.setdefault("outcomes", {})
        return value

    def _save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._state, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        tmp.replace(self.path)

    @staticmethod
    def canonical_context(context: dict[str, Any] | None) -> dict[str, Any]:
        raw = context if isinstance(context, dict) else {}
        result = {
            "period": str(raw.get("period") or "unknown").strip().lower() or "unknown",
            "weather": str(raw.get("weather") or "unknown").strip().lower() or "unknown",
            "region_id": str(raw.get("region_id") or "unknown").strip() or "unknown",
        }
        try:
            danger = float(raw.get("danger_level", 0.0))
        except (TypeError, ValueError):
            danger = 0.0
        danger = min(1.0, max(0.0, danger))
        result["danger_band"] = "high" if danger >= 0.67 else "medium" if danger >= 0.34 else "low"
        return result

    @classmethod
    def context_key(cls, context: dict[str, Any] | None) -> str:
        canonical = cls.canonical_context(context)
        return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _key(npc_id: str, need: str, target_entity_id: str) -> str:
        return f"{npc_id}\u001f{need}\u001f{target_entity_id}"

    @classmethod
    def _contextual_key(cls, npc_id: str, need: str, target_entity_id: str, context: dict[str, Any] | None) -> str:
        return f"{npc_id}\u001f{need}\u001f{cls.context_key(context)}\u001f{target_entity_id}"

    @staticmethod
    def _update_mean(current: dict[str, Any] | None, reward: float) -> tuple[int, float]:
        row = current if isinstance(current, dict) else {}
        count = int(row.get("count", 0))
        mean = float(row.get("mean_satisfaction", 0.0))
        new_count = count + 1
        return new_count, mean + (reward - mean) / new_count

    def observe(self, *, outcome_id: str, npc_id: str, need: str, target_entity_id: str, satisfaction: float,
                plan_id: str | None = None, proposal_id: str | None = None,
                context: dict[str, Any] | None = None) -> dict[str, Any]:
        outcome_id = str(outcome_id or "").strip()
        npc_id = str(npc_id or "").strip()
        need = str(need or "").strip().lower()
        target_entity_id = str(target_entity_id or "").strip()
        if not outcome_id or not npc_id or not need or not target_entity_id:
            raise ValueError("outcome_id, npc_id, need and target_entity_id are required")
        outcomes = self._state.setdefault("outcomes", {})
        if outcome_id in outcomes:
            return deepcopy(outcomes[outcome_id])

        reward = min(1.0, max(0.0, float(satisfaction)))
        canonical_context = self.canonical_context(context)
        entries = self._state.setdefault("entries", {})
        global_key = self._key(npc_id, need, target_entity_id)
        global_count, global_mean = self._update_mean(entries.get(global_key), reward)
        entries[global_key] = {
            "npc_id": npc_id, "need": need, "target_entity_id": target_entity_id,
            "count": global_count, "mean_satisfaction": global_mean,
            "last_outcome_id": outcome_id,
            "last_plan_id": str(plan_id or "").strip() or None,
            "last_proposal_id": str(proposal_id or "").strip() or None,
        }
        context_entries = self._state.setdefault("context_entries", {})
        contextual_key = self._contextual_key(npc_id, need, target_entity_id, canonical_context)
        context_count, context_mean = self._update_mean(context_entries.get(contextual_key), reward)
        context_entries[contextual_key] = {
            "npc_id": npc_id, "need": need, "target_entity_id": target_entity_id,
            "context": canonical_context, "context_key": self.context_key(canonical_context),
            "count": context_count, "mean_satisfaction": context_mean,
            "last_outcome_id": outcome_id,
            "last_plan_id": str(plan_id or "").strip() or None,
            "last_proposal_id": str(proposal_id or "").strip() or None,
        }
        outcome = {
            "outcome_id": outcome_id,
            "npc_id": npc_id,
            "need": need,
            "target_entity_id": target_entity_id,
            "satisfaction": reward,
            "context": canonical_context,
            # v1 compatibility aliases remain the global values.
            "count_after": global_count,
            "mean_satisfaction_after": global_mean,
            "global_count_after": global_count,
            "global_mean_satisfaction_after": global_mean,
            "context_count_after": context_count,
            "context_mean_satisfaction_after": context_mean,
            "plan_id": str(plan_id or "").strip() or None,
            "proposal_id": str(proposal_id or "").strip() or None,
        }
        outcomes[outcome_id] = outcome
        self._save()
        return deepcopy(outcome)

    def stats(self, npc_id: str, need: str, target_entity_id: str) -> dict[str, Any] | None:
        key = self._key(str(npc_id), str(need).lower(), str(target_entity_id))
        row = self._state.get("entries", {}).get(key)
        return deepcopy(row) if isinstance(row, dict) else None

    def contextual_stats(self, npc_id: str, need: str, target_entity_id: str,
                         context: dict[str, Any] | None) -> dict[str, Any] | None:
        key = self._contextual_key(str(npc_id), str(need).lower(), str(target_entity_id), context)
        row = self._state.get("context_entries", {}).get(key)
        return deepcopy(row) if isinstance(row, dict) else None

    def rank_targets(self, npc_id: str, need: str, target_ids: list[str],
                     context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        canonical_context = self.canonical_context(context)
        for target_id in sorted({str(v).strip() for v in target_ids if str(v).strip()}):
            global_stat = self.stats(npc_id, need, target_id) or {"count": 0, "mean_satisfaction": 0.0}
            contextual_stat = self.contextual_stats(npc_id, need, target_id, canonical_context) or {"count": 0, "mean_satisfaction": 0.0}
            global_count = int(global_stat.get("count", 0))
            global_mean = float(global_stat.get("mean_satisfaction", 0.0))
            context_count = int(contextual_stat.get("count", 0))
            context_mean = float(contextual_stat.get("mean_satisfaction", 0.0))
            exploring = context_count < self.exploration_samples
            use_context = context_count >= self.contextual_min_samples
            effective_mean = context_mean if use_context else global_mean
            rows.append({
                "target_entity_id": target_id,
                "context": canonical_context,
                # v1 compatibility aliases remain global evidence.
                "count": global_count,
                "mean_satisfaction": global_mean,
                "context_count": context_count,
                "context_mean_satisfaction": context_mean,
                "global_count": global_count,
                "global_mean_satisfaction": global_mean,
                "effective_mean_satisfaction": effective_mean,
                "evidence_source": "context" if use_context else "global_fallback",
                "exploring": exploring,
            })
        rows.sort(key=lambda row: (
            0 if row["exploring"] else 1,
            row["context_count"] if row["exploring"] else 0,
            0.0 if row["exploring"] else -row["effective_mean_satisfaction"],
            0 if row["exploring"] else -row["context_count"],
            0 if row["exploring"] else -row["global_count"],
            row["target_entity_id"],
        ))
        return rows

    def choose_target(self, npc_id: str, need: str, target_ids: list[str],
                      context: dict[str, Any] | None = None) -> str | None:
        ranked = self.rank_targets(npc_id, need, target_ids, context=context)
        return str(ranked[0]["target_entity_id"]) if ranked else None

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)
