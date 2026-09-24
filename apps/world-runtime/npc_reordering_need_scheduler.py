from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from npc_need_scheduler import NpcNeedScheduler


class NpcReorderingNeedScheduler(NpcNeedScheduler):
    """Need scheduler with one bounded, auditable horizon reorder.

    The base scheduler remains the compatibility path. This subclass may replace
    the currently selected need with a single prerequisite need only when the
    chosen strategy carries a declarative goal_sequence in defer_current mode.
    Reordering is fail-closed, target-aware, cooldown-aware and never recursive.
    """

    def _horizon_prerequisite(self, strategy: dict[str, Any] | None, current_need: str) -> dict[str, Any] | None:
        if not isinstance(strategy, dict):
            return None
        sequence = strategy.get("goal_sequence")
        if not isinstance(sequence, dict) or str(sequence.get("mode") or "") != "defer_current":
            return None
        goals = sequence.get("goals")
        if not isinstance(goals, list) or not goals:
            return None
        first = goals[0] if isinstance(goals[0], dict) else None
        if first is None:
            return None
        need = str(first.get("need") or "").strip().lower()
        target_id = str(first.get("target_entity_id") or "").strip()
        if not need or need == current_need or need not in self.DEFAULT_PRIORITIES or not target_id:
            return None
        if self._entity(target_id) is None:
            return None
        return {
            "need": need,
            "target_entity_id": target_id,
            "goal_sequence": deepcopy(sequence),
        }

    def _prepare_need(
        self,
        *,
        entity: dict[str, Any],
        need: str,
        severity: float,
        priority: int,
        utility: float,
        values: dict[str, float],
        context: dict[str, Any],
        tick: int,
    ) -> dict[str, Any]:
        intent, target_ranking, strategy, strategy_ranking = self._intent_for(entity, need, context)
        if intent is None:
            return {
                "need": need,
                "severity": severity,
                "priority": priority,
                "utility": utility,
                "intent": None,
                "target_ranking": target_ranking,
                "strategy": strategy,
                "strategy_ranking": strategy_ranking,
                "selected_target_id": None,
                "composite_plan": None,
            }

        selected_target_id = str(intent.get("target_entity_id") or "")
        if not selected_target_id:
            selected_target_id = str((strategy or {}).get("target_entity_id") or "")
        composite_plan = None
        if selected_target_id and self._composite_enabled():
            chosen, composite_ranking, compiled = self._choose_composite(
                entity=entity,
                need=need,
                target_id=selected_target_id,
                context=context,
                target_ranking=target_ranking,
                severity=severity,
            )
            if chosen is not None:
                strategy = chosen
                strategy_ranking = composite_ranking
                composite_plan = compiled

        return {
            "need": need,
            "severity": severity,
            "priority": priority,
            "utility": utility,
            "intent": intent,
            "target_ranking": target_ranking,
            "strategy": strategy,
            "strategy_ranking": strategy_ranking,
            "selected_target_id": selected_target_id,
            "composite_plan": composite_plan,
        }

    def evaluate_tick(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        results: list[dict[str, Any]] = []
        for npc_id in self.npc_ids:
            entity = self._entity(npc_id)
            if entity is None:
                continue
            values = self._need_values(entity)
            candidates = [
                (name, value, self.DEFAULT_PRIORITIES[name], value * self.DEFAULT_PRIORITIES[name])
                for name, value in values.items()
                if value >= self.threshold
            ]
            if not candidates:
                continue
            candidates.sort(key=lambda item: (-item[3], -item[2], item[0]))
            original_need, original_severity, original_priority, original_utility = candidates[0]
            last_tick = self._last_tick(npc_id, original_need)
            if last_tick is not None and tick - last_tick < self.cooldown_ticks:
                results.append({"npc_id": npc_id, "need": original_need, "status": "cooldown", "tick": tick})
                continue

            context = self._context_for(entity, tick=tick)
            prepared = self._prepare_need(
                entity=entity,
                need=original_need,
                severity=original_severity,
                priority=original_priority,
                utility=original_utility,
                values=values,
                context=context,
                tick=tick,
            )
            if prepared["intent"] is None:
                row = {
                    "need_schema": "npc_need_v7",
                    "npc_id": npc_id,
                    "need": original_need,
                    "original_need": original_need,
                    "horizon_reordered": False,
                    "severity": original_severity,
                    "priority": original_priority,
                    "utility": original_utility,
                    "tick": tick,
                    "status": "no_target",
                    "learning_context": deepcopy(context),
                    "target_ranking": prepared["target_ranking"],
                    "strategy": prepared["strategy"],
                    "strategy_ranking": prepared["strategy_ranking"],
                    "proposal_id": None,
                    "plan_id": None,
                    "strategy_execution_id": None,
                    "created_at_unix": time.time(),
                }
                self._append(row)
                results.append(row)
                continue

            reorder_source_sequence = None
            prerequisite = self._horizon_prerequisite(prepared["strategy"], original_need)
            if prerequisite is not None:
                deferred_need = str(prerequisite["need"])
                deferred_last_tick = self._last_tick(npc_id, deferred_need)
                deferred_in_cooldown = deferred_last_tick is not None and tick - deferred_last_tick < self.cooldown_ticks
                if not deferred_in_cooldown:
                    deferred_severity = float(values.get(deferred_need, 0.0))
                    deferred_priority = int(self.DEFAULT_PRIORITIES[deferred_need])
                    deferred_utility = deferred_severity * deferred_priority
                    deferred = self._prepare_need(
                        entity=entity,
                        need=deferred_need,
                        severity=deferred_severity,
                        priority=deferred_priority,
                        utility=deferred_utility,
                        values=values,
                        context=context,
                        tick=tick,
                    )
                    if deferred["intent"] is not None:
                        actual_target = str(deferred["selected_target_id"] or "")
                        expected_target = str(prerequisite["target_entity_id"] or "")
                        if actual_target and actual_target == expected_target:
                            reorder_source_sequence = deepcopy(prerequisite["goal_sequence"])
                            prepared = deferred

            need = str(prepared["need"])
            severity = float(prepared["severity"])
            priority = int(prepared["priority"])
            utility = float(prepared["utility"])
            intent = prepared["intent"]
            target_ranking = prepared["target_ranking"]
            strategy = prepared["strategy"]
            strategy_ranking = prepared["strategy_ranking"]
            selected_target_id = str(prepared["selected_target_id"] or "")
            composite_plan = prepared["composite_plan"]
            horizon_reordered = need != original_need

            strategy_id = str((strategy or {}).get("strategy_id") or "direct")
            goal_intent = {
                "intent": "move_to_entity",
                "actor_entity_id": npc_id,
                "target_entity_id": selected_target_id,
                "need": need,
                "learning_context": deepcopy(context),
                "strategy_id": strategy_id,
            }
            bucket = tick // max(1, self.cooldown_ticks or 1)
            idem = (
                f"npc-need:{npc_id}:{original_need}:reorder:{need}:{bucket}"
                if horizon_reordered
                else f"npc-need:{npc_id}:{need}:{bucket}"
            )
            proposal = self.proposals.propose(
                origin="npc_need",
                proposer_id=f"npc:{npc_id}",
                proposal_kind="agent_intent",
                payload={"intent": deepcopy(goal_intent)},
                metadata={
                    "need": need,
                    "original_need": original_need,
                    "horizon_reordered": horizon_reordered,
                    "reorder_source_sequence": deepcopy(reorder_source_sequence),
                    "severity": severity,
                    "utility": utility,
                    "tick": tick,
                    "plan_priority": priority,
                    "selected_target_entity_id": selected_target_id,
                    "learning_context": deepcopy(context),
                    "target_ranking": deepcopy(target_ranking),
                    "strategy_id": strategy_id,
                    "strategy": deepcopy(strategy),
                    "strategy_ranking": deepcopy(strategy_ranking),
                    "strategy_plan": deepcopy(composite_plan),
                },
                idempotency_key=idem,
            )
            if proposal.get("status") == "proposed":
                reason = f"deterministic need threshold reached: {severity:.3f}; utility={utility:.3f}; strategy={strategy_id}"
                if horizon_reordered:
                    reason += f"; horizon reordered {original_need}->{need}"
                proposal = self.proposals.approve(
                    str(proposal["proposal_id"]),
                    decided_by=f"need_policy:{need}",
                    reason=reason,
                )

            principal = {
                "source": "npc_need",
                "actor_id": npc_id,
                "authority": "entity_agent",
                "subject_entity_id": npc_id,
            }
            plan_id = None
            strategy_execution_id = None
            if composite_plan is not None:
                start_fn = getattr(self.strategy_executor, "start", None)
                if callable(start_fn):
                    execution = start_fn(
                        deepcopy(composite_plan),
                        principal=principal,
                        proposer_id=f"npc:{npc_id}",
                        proposal_id=str(proposal["proposal_id"]),
                        priority=priority,
                        idempotency_key=f"npc-need-strategy:{proposal['proposal_id']}",
                    )
                    strategy_execution_id = execution.get("strategy_execution_id")
            if strategy_execution_id is None:
                plan = self.plans.schedule(
                    intent=deepcopy(intent),
                    principal=principal,
                    proposer_id=f"npc:{npc_id}",
                    proposal_id=str(proposal["proposal_id"]),
                    idempotency_key=f"npc-need-plan:{proposal['proposal_id']}",
                    priority=priority,
                )
                plan_id = plan.get("plan_id")

            row = {
                "need_schema": "npc_need_v7",
                "npc_id": npc_id,
                "need": need,
                "original_need": original_need,
                "horizon_reordered": horizon_reordered,
                "reorder_source_sequence": deepcopy(reorder_source_sequence),
                "severity": severity,
                "priority": priority,
                "utility": utility,
                "tick": tick,
                "status": "scheduled",
                "selected_target_entity_id": selected_target_id,
                "learning_context": deepcopy(context),
                "target_ranking": deepcopy(target_ranking),
                "strategy_id": strategy_id,
                "strategy": deepcopy(strategy),
                "strategy_ranking": deepcopy(strategy_ranking),
                "strategy_plan": deepcopy(composite_plan),
                "proposal_id": proposal.get("proposal_id"),
                "plan_id": plan_id,
                "strategy_execution_id": strategy_execution_id,
                "created_at_unix": time.time(),
            }
            self._append(row)
            results.append(row)
        return results
