from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcNeedDynamics:
    """Compact persistent need-state dynamics driven by logical world ticks.

    Need values live outside full cold entity payloads to avoid rewriting an
    entity every tick. The cold store remains the source for identity, region and
    configured targets. This component never creates plans or mutates world state.
    """

    DEFAULT_RATES = {
        "safety": -0.0030,
        "energy": 0.0020,
        "social": 0.0015,
        "curiosity": 0.0010,
    }

    def __init__(
        self,
        path: Path,
        store: Any,
        *,
        npc_ids: list[str],
        world_provider: Any | None = None,
        rates: dict[str, float] | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.npc_ids = tuple(sorted({str(v).strip() for v in npc_ids if str(v).strip()}))
        self.world_provider = world_provider
        self.rates = dict(self.DEFAULT_RATES)
        for key, value in dict(rates or {}).items():
            if key in self.rates:
                self.rates[key] = float(value)
        self._state = self._load()

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "npc_need_state_v1", "last_tick": 0, "npcs": {}}
        with self.path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        if not isinstance(value, dict):
            raise ValueError("invalid NPC need dynamics state")
        value.setdefault("schema", "npc_need_state_v1")
        value.setdefault("last_tick", 0)
        value.setdefault("npcs", {})
        return value

    def _save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._state, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        tmp.replace(self.path)

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        getter = getattr(self.store, "get_entity", None)
        if not callable(getter):
            return None
        return getter(entity_id)

    @staticmethod
    def _initial_needs(entity: dict[str, Any]) -> dict[str, float]:
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        raw = props.get("needs") if isinstance(props.get("needs"), dict) else {}
        result: dict[str, float] = {}
        for name in NpcNeedDynamics.DEFAULT_RATES:
            try:
                result[name] = NpcNeedDynamics._clamp(float(raw.get(name, 0.0)))
            except (TypeError, ValueError):
                result[name] = 0.0
        return result

    def get_needs(self, npc_id: str) -> dict[str, float] | None:
        row = dict(self._state.get("npcs", {})).get(str(npc_id))
        if not isinstance(row, dict):
            return None
        raw = row.get("needs") if isinstance(row.get("needs"), dict) else {}
        return {name: self._clamp(raw.get(name, 0.0)) for name in self.DEFAULT_RATES}

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._state)

    def _same_region(self, entity: dict[str, Any], target_field: str) -> bool:
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        target_id = str(props.get(target_field) or "").strip()
        if not target_id:
            return False
        target = self._entity(target_id)
        if target is None:
            return False
        return str(target.get("region_id") or "") == str(entity.get("region_id") or "")

    def _danger_level(self, entity: dict[str, Any]) -> float:
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        try:
            local = self._clamp(float(props.get("danger_level", 0.0)))
        except (TypeError, ValueError):
            local = 0.0
        world = 0.0
        if callable(self.world_provider):
            value = self.world_provider()
            env = value.get("environment") if isinstance(value, dict) and isinstance(value.get("environment"), dict) else {}
            try:
                world = self._clamp(float(env.get("danger_level", 0.0)))
            except (TypeError, ValueError):
                world = 0.0
        return max(local, world)

    def advance_tick(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        last_tick = int(self._state.get("last_tick", 0))
        if tick <= last_tick:
            return []

        results: list[dict[str, Any]] = []
        npcs = self._state.setdefault("npcs", {})
        for npc_id in self.npc_ids:
            entity = self._entity(npc_id)
            if entity is None:
                continue
            current_row = npcs.get(npc_id) if isinstance(npcs.get(npc_id), dict) else None
            needs = self._initial_needs(entity) if current_row is None else {
                name: self._clamp((current_row.get("needs") or {}).get(name, 0.0))
                for name in self.DEFAULT_RATES
            }
            before = dict(needs)

            needs["safety"] = self._clamp(needs["safety"] + self.rates["safety"] + self._danger_level(entity) * 0.020)
            needs["energy"] = self._clamp(needs["energy"] + (-0.020 if self._same_region(entity, "rest_target_entity_id") else self.rates["energy"]))
            needs["social"] = self._clamp(needs["social"] + (-0.015 if self._same_region(entity, "social_target_entity_id") else self.rates["social"]))
            needs["curiosity"] = self._clamp(needs["curiosity"] + (-0.020 if self._same_region(entity, "curiosity_target_entity_id") else self.rates["curiosity"]))

            npcs[npc_id] = {"needs": needs, "last_tick": tick}
            results.append({"npc_id": npc_id, "tick": tick, "before": before, "after": dict(needs)})

        self._state["last_tick"] = tick
        self._save()
        return results
