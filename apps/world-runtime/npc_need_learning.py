from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcNeedLearning:
    """Deterministic incremental outcome learning for need-driven targets.

    Learns an online mean observed satisfaction for each
    (npc_id, need, target_entity_id) tuple. No neural network and no randomness.
    Selection prefers under-sampled valid targets first up to ``exploration_samples``;
    afterwards it prefers the highest empirical mean, then sample count, then id.
    """

    def __init__(self, path: Path, *, exploration_samples: int = 2) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.exploration_samples = max(0, int(exploration_samples))
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "npc_need_learning_v1", "entries": {}, "outcomes": {}}
        with self.path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        if not isinstance(value, dict):
            raise ValueError("invalid NPC need learning state")
        value.setdefault("schema", "npc_need_learning_v1")
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
    def _key(npc_id: str, need: str, target_entity_id: str) -> str:
        return f"{npc_id}\u001f{need}\u001f{target_entity_id}"

    def observe(
        self,
        *,
        outcome_id: str,
        npc_id: str,
        need: str,
        target_entity_id: str,
        satisfaction: float,
        plan_id: str | None = None,
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
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
        entries = self._state.setdefault("entries", {})
        key = self._key(npc_id, need, target_entity_id)
        current = entries.get(key) if isinstance(entries.get(key), dict) else {}
        count = int(current.get("count", 0))
        mean = float(current.get("mean_satisfaction", 0.0))
        new_count = count + 1
        new_mean = mean + (reward - mean) / new_count
        row = {
            "npc_id": npc_id,
            "need": need,
            "target_entity_id": target_entity_id,
            "count": new_count,
            "mean_satisfaction": new_mean,
            "last_outcome_id": outcome_id,
            "last_plan_id": str(plan_id or "").strip() or None,
            "last_proposal_id": str(proposal_id or "").strip() or None,
        }
        entries[key] = row
        outcome = {
            "outcome_id": outcome_id,
            "npc_id": npc_id,
            "need": need,
            "target_entity_id": target_entity_id,
            "satisfaction": reward,
            "count_after": new_count,
            "mean_satisfaction_after": new_mean,
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

    def rank_targets(self, npc_id: str, need: str, target_ids: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for target_id in sorted({str(v).strip() for v in target_ids if str(v).strip()}):
            stat = self.stats(npc_id, need, target_id) or {
                "count": 0,
                "mean_satisfaction": 0.0,
            }
            count = int(stat.get("count", 0))
            mean = float(stat.get("mean_satisfaction", 0.0))
            exploring = count < self.exploration_samples
            rows.append({
                "target_entity_id": target_id,
                "count": count,
                "mean_satisfaction": mean,
                "exploring": exploring,
            })

        # Deterministic exploration: least-sampled targets first until each has
        # reached the minimum sample count. Exploitation then chooses empirical
        # mean, followed by evidence count and stable entity id.
        rows.sort(key=lambda row: (
            0 if row["exploring"] else 1,
            row["count"] if row["exploring"] else 0,
            0.0 if row["exploring"] else -row["mean_satisfaction"],
            0 if row["exploring"] else -row["count"],
            row["target_entity_id"],
        ))
        return rows

    def choose_target(self, npc_id: str, need: str, target_ids: list[str]) -> str | None:
        ranked = self.rank_targets(npc_id, need, target_ids)
        return str(ranked[0]["target_entity_id"]) if ranked else None

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)
