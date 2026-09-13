from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcStrategyCompileError(ValueError):
    pass


class NpcStrategyCompiler:
    """Compile a chosen composite strategy into deterministic semantic phases.

    Compilation grants no authority and performs no world mutation. Only the
    terminal movement phase is eligible to satisfy the originating need; earlier
    waypoints remain causal strategy phases but cannot trigger need outcomes.
    """

    ALLOWED_PHASES = frozenset({"move_to_entity", "wait_ticks"})

    def compile(
        self,
        *,
        actor_entity_id: str,
        need: str,
        target_entity_id: str,
        strategy: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        actor = str(actor_entity_id or "").strip()
        need_name = str(need or "").strip().lower()
        target = str(target_entity_id or "").strip()
        strategy_id = str(strategy.get("strategy_id") or "").strip()
        raw_phases = strategy.get("phases") if isinstance(strategy.get("phases"), list) else []
        if not actor or not need_name or not target or not strategy_id or not raw_phases:
            raise NpcStrategyCompileError("actor, need, target, strategy_id and phases are required")

        phases: list[dict[str, Any]] = []
        last_index = len(raw_phases) - 1
        for index, raw in enumerate(raw_phases):
            if not isinstance(raw, dict):
                raise NpcStrategyCompileError(f"phase {index} must be an object")
            kind = str(raw.get("kind") or "").strip().lower()
            if kind not in self.ALLOWED_PHASES:
                raise NpcStrategyCompileError(f"unsupported strategy phase: {kind!r}")
            outcome_eligible = index == last_index and kind == "move_to_entity"
            if kind == "move_to_entity":
                phase_target = str(raw.get("target_entity_id") or "").strip()
                if not phase_target:
                    raise NpcStrategyCompileError(f"phase {index} target_entity_id is required")
                intent = {
                    "intent": "move_to_entity",
                    "actor_entity_id": actor,
                    "target_entity_id": phase_target,
                    "need": need_name,
                    "need_outcome_eligible": outcome_eligible,
                    "learning_context": deepcopy(context or {}),
                    "strategy_id": strategy_id,
                    "strategy_phase_index": index,
                }
            else:
                ticks = max(0, int(raw.get("ticks", 0)))
                if ticks <= 0:
                    raise NpcStrategyCompileError(f"phase {index} wait ticks must be positive")
                intent = {
                    "intent": "wait_ticks",
                    "actor_entity_id": actor,
                    "ticks": ticks,
                    "need": need_name,
                    "need_outcome_eligible": False,
                    "learning_context": deepcopy(context or {}),
                    "strategy_id": strategy_id,
                    "strategy_phase_index": index,
                }
            phases.append({"phase_index": index, "kind": kind, "intent": intent})

        return {
            "strategy_plan_schema": "npc_strategy_plan_v1",
            "strategy_id": strategy_id,
            "actor_entity_id": actor,
            "need": need_name,
            "target_entity_id": target,
            "context": deepcopy(context or {}),
            "expected_value": strategy.get("expected_value"),
            "predicted_satisfaction": strategy.get("predicted_satisfaction"),
            "phases": phases,
        }
