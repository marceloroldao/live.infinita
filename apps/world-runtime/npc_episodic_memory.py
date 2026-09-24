from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcEpisodicMemory:
    """Append-only deterministic episodic memory for autonomous NPC experience.

    Episodes preserve concrete experience separately from statistical learning.
    Recall is deliberately local and deterministic: it ranks past episodes by
    exact semantic/context matches and then by recency, without an LLM or vector
    database dependency.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    @staticmethod
    def _context(raw: dict[str, Any] | None) -> dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        result: dict[str, Any] = {}
        for key in ("period", "weather", "region_id"):
            value = str(raw.get(key) or "").strip()
            if value:
                result[key] = value
        try:
            danger = min(1.0, max(0.0, float(raw.get("danger_level", 0.0))))
        except (TypeError, ValueError):
            danger = 0.0
        result["danger_level"] = danger
        result["danger_bucket"] = int(danger * 4.0 + 1e-9)
        return result

    def remember(
        self,
        *,
        episode_id: str,
        npc_id: str,
        logical_tick: int | None,
        need: str,
        target_entity_id: str,
        strategy_id: str,
        context: dict[str, Any] | None,
        satisfaction: float,
        elapsed_ticks: int,
        preemptions: int = 0,
        replans: int = 0,
        observed_risk: float = 0.0,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        episode_id = str(episode_id or "").strip()
        npc_id = str(npc_id or "").strip()
        if not episode_id:
            raise ValueError("episode_id is required")
        if not npc_id:
            raise ValueError("npc_id is required")

        for row in self.history():
            if row.get("episode_id") == episode_id:
                return deepcopy(row)

        row = {
            "episode_schema": "npc_episode_v1",
            "episode_id": episode_id,
            "npc_id": npc_id,
            "logical_tick": int(logical_tick) if logical_tick is not None else None,
            "need": str(need or "").strip().lower(),
            "target_entity_id": str(target_entity_id or "").strip(),
            "strategy_id": str(strategy_id or "direct").strip() or "direct",
            "context": self._context(context),
            "outcome": {
                "satisfaction": min(1.0, max(0.0, float(satisfaction))),
                "elapsed_ticks": max(0, int(elapsed_ticks)),
                "preemptions": max(0, int(preemptions)),
                "replans": max(0, int(replans)),
                "observed_risk": min(1.0, max(0.0, float(observed_risk))),
            },
            "source": deepcopy(source or {}),
        }
        return deepcopy(self._append(row))

    @staticmethod
    def _score(row: dict[str, Any], query: dict[str, Any]) -> int:
        score = 0
        if query.get("need") and row.get("need") == query["need"]:
            score += 16
        if query.get("target_entity_id") and row.get("target_entity_id") == query["target_entity_id"]:
            score += 8
        if query.get("strategy_id") and row.get("strategy_id") == query["strategy_id"]:
            score += 4
        context = row.get("context") if isinstance(row.get("context"), dict) else {}
        qctx = query.get("context") if isinstance(query.get("context"), dict) else {}
        for key, weight in (("period", 4), ("weather", 2), ("region_id", 2), ("danger_bucket", 1)):
            if key in qctx and context.get(key) == qctx.get(key):
                score += weight
        return score

    def recall(
        self,
        npc_id: str,
        *,
        need: str | None = None,
        target_entity_id: str | None = None,
        strategy_id: str | None = None,
        context: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        npc_id = str(npc_id or "").strip()
        if not npc_id:
            return []
        query = {
            "need": str(need or "").strip().lower(),
            "target_entity_id": str(target_entity_id or "").strip(),
            "strategy_id": str(strategy_id or "").strip(),
            "context": self._context(context),
        }
        candidates = [row for row in self.history() if row.get("npc_id") == npc_id]
        ranked = sorted(
            candidates,
            key=lambda row: (
                -self._score(row, query),
                -(int(row.get("logical_tick")) if row.get("logical_tick") is not None else -1),
                str(row.get("episode_id") or ""),
            ),
        )
        return [deepcopy(row) for row in ranked[: max(0, int(limit))]]
