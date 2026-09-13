from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcBeliefModel:
    """Deterministic evidence-weighted beliefs derived from concrete episodes.

    Beliefs are never binary facts. Each contextual risk belief keeps supporting,
    counter and neutral evidence, an online mean and a confidence that grows with
    repeated observations. Episodes remain the provenance source of every update.
    """

    def __init__(
        self,
        path: Path,
        *,
        prior_strength: float = 3.0,
        evidence_limit: int = 12,
        entity_provider: Any | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prior_strength = max(0.1, float(prior_strength))
        self.evidence_limit = max(1, int(evidence_limit))
        self.entity_provider = entity_provider

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"belief_schema": "npc_beliefs_v1", "entries": {}, "processed_episode_ids": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        value.setdefault("belief_schema", "npc_beliefs_v1")
        value.setdefault("entries", {})
        value.setdefault("processed_episode_ids", [])
        return value

    def _save(self, state: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    @staticmethod
    def _context(raw: dict[str, Any] | None) -> dict[str, str]:
        raw = raw if isinstance(raw, dict) else {}
        return {
            "region_id": str(raw.get("region_id") or "").strip(),
            "period": str(raw.get("period") or "").strip(),
            "weather": str(raw.get("weather") or "").strip(),
        }

    @classmethod
    def _key(cls, npc_id: str, context: dict[str, Any] | None) -> str:
        ctx = cls._context(context)
        return "|".join((str(npc_id).strip(), ctx["region_id"], ctx["period"], ctx["weather"]))

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        provider = self.entity_provider
        getter = getattr(provider, "get_entity", None) if provider is not None else None
        value = getter(entity_id) if callable(getter) else None
        return value if isinstance(value, dict) else None

    def _experienced_context(self, episode: dict[str, Any]) -> dict[str, str]:
        context = self._context(episode.get("context") if isinstance(episode.get("context"), dict) else {})
        target_id = str(episode.get("target_entity_id") or "").strip()
        target = self._entity(target_id) if target_id else None
        if target is not None:
            target_region = str(target.get("region_id") or "").strip()
            if target_region:
                context["region_id"] = target_region
        return context

    def observe_episode(self, episode: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(episode, dict):
            return None
        episode_id = str(episode.get("episode_id") or "").strip()
        npc_id = str(episode.get("npc_id") or "").strip()
        context = self._experienced_context(episode)
        region_id = str(context.get("region_id") or "").strip()
        if not episode_id or not npc_id or not region_id:
            return None
        outcome = episode.get("outcome") if isinstance(episode.get("outcome"), dict) else {}
        try:
            risk = min(1.0, max(0.0, float(outcome.get("observed_risk", 0.0))))
        except (TypeError, ValueError):
            risk = 0.0

        state = self._load()
        processed = {str(value) for value in state.get("processed_episode_ids", [])}
        key = self._key(npc_id, context)
        entries = state.setdefault("entries", {})
        if episode_id in processed:
            row = entries.get(key)
            return deepcopy(row) if isinstance(row, dict) else None

        row = entries.get(key)
        if not isinstance(row, dict):
            row = {
                "belief_type": "contextual_risk",
                "npc_id": npc_id,
                "context": self._context(context),
                "count": 0,
                "mean_risk": 0.0,
                "support_count": 0,
                "counter_count": 0,
                "neutral_count": 0,
                "confidence": 0.0,
                "evidence_episode_ids": [],
            }
        count = max(0, int(row.get("count", 0))) + 1
        old_mean = float(row.get("mean_risk", 0.0))
        row["mean_risk"] = old_mean + (risk - old_mean) / count
        row["count"] = count
        if risk >= 0.60:
            row["support_count"] = int(row.get("support_count", 0)) + 1
        elif risk <= 0.25:
            row["counter_count"] = int(row.get("counter_count", 0)) + 1
        else:
            row["neutral_count"] = int(row.get("neutral_count", 0)) + 1
        row["confidence"] = count / (count + self.prior_strength)
        evidence = [str(value) for value in row.get("evidence_episode_ids", []) if str(value)]
        evidence.append(episode_id)
        row["evidence_episode_ids"] = evidence[-self.evidence_limit :]
        row["last_episode_id"] = episode_id
        row["last_logical_tick"] = episode.get("logical_tick")
        entries[key] = row
        processed.add(episode_id)
        state["processed_episode_ids"] = sorted(processed)
        self._save(state)
        return deepcopy(row)

    def risk_belief(self, npc_id: str, context: dict[str, Any] | None) -> dict[str, Any] | None:
        npc_id = str(npc_id or "").strip()
        if not npc_id:
            return None
        row = self._load().get("entries", {}).get(self._key(npc_id, context))
        return deepcopy(row) if isinstance(row, dict) else None

    def beliefs(self, npc_id: str | None = None) -> list[dict[str, Any]]:
        rows = [deepcopy(row) for row in self._load().get("entries", {}).values() if isinstance(row, dict)]
        if npc_id is not None:
            wanted = str(npc_id).strip()
            rows = [row for row in rows if row.get("npc_id") == wanted]
        rows.sort(key=lambda row: (
            str(row.get("npc_id") or ""),
            str((row.get("context") or {}).get("region_id") or ""),
            str((row.get("context") or {}).get("period") or ""),
            str((row.get("context") or {}).get("weather") or ""),
        ))
        return rows
