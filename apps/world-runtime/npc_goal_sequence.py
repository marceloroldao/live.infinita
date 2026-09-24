from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcGoalSequence:
    """Convert horizon recommendations into a declarative goal sequence.

    The sequence is planning metadata only. It does not create proposals, plans,
    mutations, outcomes, memories or learning records. Execution authority stays
    with the need scheduler and plan stack.
    """

    TARGET_FIELDS = {
        "safety": "safety_target_entity_id",
        "energy": "rest_target_entity_id",
        "social": "social_target_entity_id",
        "curiosity": "curiosity_target_entity_id",
    }

    @staticmethod
    def _properties(entity: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(entity, dict):
            return {}
        value = entity.get("properties")
        return value if isinstance(value, dict) else {}

    def _target_for(self, entity: dict[str, Any], need: str) -> str | None:
        field = self.TARGET_FIELDS.get(need)
        if not field:
            return None
        value = str(self._properties(entity).get(field) or "").strip()
        return value or None

    def build(
        self,
        *,
        npc_entity: dict[str, Any],
        current_need: str,
        current_target_entity_id: str,
        horizon: dict[str, Any] | None,
    ) -> dict[str, Any]:
        npc_id = str(npc_entity.get("id") or "").strip()
        current_need = str(current_need or "").strip().lower()
        current_target = str(current_target_entity_id or "").strip()
        raw_horizon = horizon if isinstance(horizon, dict) else {}
        defer_to = str(raw_horizon.get("defer_to_need") or "").strip().lower() or None
        next_need = str(raw_horizon.get("next_urgent_need") or "").strip().lower() or None

        current_goal = {
            "need": current_need,
            "target_entity_id": current_target or self._target_for(npc_entity, current_need),
            "role": "current",
        }
        goals: list[dict[str, Any]] = []
        mode = "current_only"

        if defer_to and defer_to != current_need:
            defer_target = self._target_for(npc_entity, defer_to)
            if defer_target:
                goals.append({
                    "need": defer_to,
                    "target_entity_id": defer_target,
                    "role": "prerequisite",
                })
                goals.append(current_goal)
                mode = "defer_current"
            else:
                goals.append(current_goal)
                mode = "defer_target_missing"
        else:
            goals.append(current_goal)
            if next_need and next_need != current_need:
                next_target = self._target_for(npc_entity, next_need)
                if next_target:
                    goals.append({
                        "need": next_need,
                        "target_entity_id": next_target,
                        "role": "follow_up",
                    })
                    mode = "current_then_follow_up"

        return {
            "goal_sequence_schema": "npc_goal_sequence_v1",
            "npc_id": npc_id,
            "mode": mode,
            "goals": deepcopy(goals),
            "source_horizon": deepcopy(raw_horizon),
            "mutates_state": False,
        }
