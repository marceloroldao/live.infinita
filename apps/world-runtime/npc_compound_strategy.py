from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcCompoundStrategyCatalog:
    """Build and choose deterministic compound alternatives for need-driven movement.

    This layer does not mutate world state and does not execute plans. It only
    describes semantically explicit strategy alternatives. Every resulting plan
    still passes through the ordinary planner, scheduler, arbiter and Mutation Gate.
    """

    def __init__(self, store: Any, *, high_risk_threshold: float = 0.67) -> None:
        self.store = store
        self.high_risk_threshold = min(1.0, max(0.0, float(high_risk_threshold)))

    def _entity_exists(self, entity_id: str) -> bool:
        getter = getattr(self.store, "get_entity", None)
        return bool(entity_id and callable(getter) and getter(entity_id) is not None)

    def alternatives(
        self,
        *,
        actor_entity_id: str,
        need: str,
        target_entity_id: str,
        actor_properties: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        actor_id = str(actor_entity_id or "").strip()
        target_id = str(target_entity_id or "").strip()
        if not actor_id or not target_id or not self._entity_exists(target_id):
            return []
        props = actor_properties if isinstance(actor_properties, dict) else {}
        base = {
            "actor_entity_id": actor_id,
            "target_entity_id": target_id,
            "need": str(need or "").strip().lower(),
            "learning_context": deepcopy(context or {}),
        }
        rows = [{
            "strategy_id": "direct",
            "strategy_kind": "direct",
            "intent": {"intent": "move_to_entity", **deepcopy(base)},
            "via_entity_ids": [],
        }]

        shelter_id = str(
            props.get("strategy_shelter_entity_id")
            or props.get("safety_target_entity_id")
            or ""
        ).strip()
        if shelter_id and shelter_id != target_id and self._entity_exists(shelter_id):
            rows.append({
                "strategy_id": f"via:{shelter_id}",
                "strategy_kind": "via_shelter",
                "intent": {
                    "intent": "move_via_entities",
                    **deepcopy(base),
                    "via_entity_ids": [shelter_id],
                },
                "via_entity_ids": [shelter_id],
            })
        return rows

    def choose(
        self,
        *,
        actor_entity_id: str,
        need: str,
        target_entity_id: str,
        actor_properties: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        rows = self.alternatives(
            actor_entity_id=actor_entity_id,
            need=need,
            target_entity_id=target_entity_id,
            actor_properties=actor_properties,
            context=context,
        )
        if not rows:
            return None, []
        raw_context = context if isinstance(context, dict) else {}
        try:
            danger = min(1.0, max(0.0, float(raw_context.get("danger_level", 0.0))))
        except (TypeError, ValueError):
            danger = 0.0
        preferred_kind = "via_shelter" if danger >= self.high_risk_threshold else "direct"
        selected = next((row for row in rows if row.get("strategy_kind") == preferred_kind), rows[0])
        ranked = []
        for row in rows:
            copy = deepcopy(row)
            copy["selected"] = row.get("strategy_id") == selected.get("strategy_id")
            copy["selection_reason"] = (
                f"danger={danger:.3f} >= {self.high_risk_threshold:.3f}"
                if preferred_kind == "via_shelter"
                else f"danger={danger:.3f} < {self.high_risk_threshold:.3f}"
            )
            ranked.append(copy)
        ranked.sort(key=lambda row: (0 if row.get("selected") else 1, str(row.get("strategy_id") or "")))
        return deepcopy(selected), ranked

    @staticmethod
    def attach_value(
        alternatives: list[dict[str, Any]],
        *,
        direct_value: float,
        shelter_risk_relief: float = 0.15,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in alternatives:
            row = deepcopy(raw)
            value = float(direct_value)
            if row.get("strategy_kind") == "via_shelter":
                value += max(0.0, float(shelter_risk_relief))
            row["strategy_value"] = value
            rows.append(row)
        rows.sort(key=lambda row: (-float(row.get("strategy_value", 0.0)), str(row.get("strategy_id") or "")))
        return rows
