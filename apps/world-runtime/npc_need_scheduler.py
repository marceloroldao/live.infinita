from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from plan_scheduler import PlanScheduler
from proposal_ledger import ProposalLedger


class NpcNeedScheduler:
    """Turn bounded NPC internal needs into semantic intent proposals."""

    DEFAULT_PRIORITIES = {"safety": 1000, "energy": 700, "social": 400, "curiosity": 200}
    TARGET_FIELDS = {
        "safety": "safety_target_entity_id",
        "energy": "rest_target_entity_id",
        "social": "social_target_entity_id",
        "curiosity": "curiosity_target_entity_id",
    }
    TARGET_LIST_FIELDS = {
        "safety": "safety_target_entity_ids",
        "energy": "rest_target_entity_ids",
        "social": "social_target_entity_ids",
        "curiosity": "curiosity_target_entity_ids",
    }

    def __init__(
        self,
        path: Path,
        proposal_ledger: ProposalLedger,
        plan_scheduler: PlanScheduler,
        *,
        npc_ids: list[str],
        threshold: float = 0.70,
        cooldown_ticks: int = 20,
        need_state_provider: Any | None = None,
        learning_provider: Any | None = None,
        world_provider: Any | None = None,
        strategy_provider: Any | None = None,
        compound_strategy_provider: Any | None = None,
        composite_strategy_provider: Any | None = None,
        strategy_compiler: Any | None = None,
        strategy_executor: Any | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.proposals = proposal_ledger
        self.plans = plan_scheduler
        self.npc_ids = tuple(sorted({str(v).strip() for v in npc_ids if str(v).strip()}))
        self.threshold = float(threshold)
        self.cooldown_ticks = max(0, int(cooldown_ticks))
        self.need_state_provider = need_state_provider
        self.learning_provider = learning_provider
        self.world_provider = world_provider
        self.strategy_provider = strategy_provider
        self.compound_strategy_provider = compound_strategy_provider
        self.composite_strategy_provider = composite_strategy_provider
        self.strategy_compiler = strategy_compiler
        self.strategy_executor = strategy_executor

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
        return rows

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        planner = self.plans.planner
        store = getattr(planner, "store", None)
        if store is None or not hasattr(store, "get_entity"):
            return None
        return store.get_entity(entity_id)

    def _world(self) -> dict[str, Any]:
        if callable(self.world_provider):
            value = self.world_provider()
            return value if isinstance(value, dict) else {}
        guarded = getattr(self.plans, "guarded", None)
        engine = getattr(guarded, "engine", None)
        loader = getattr(engine, "load_world", None)
        if callable(loader):
            value = loader()
            return value if isinstance(value, dict) else {}
        return {}

    def _context_for(self, entity: dict[str, Any]) -> dict[str, Any]:
        world = self._world()
        env = world.get("environment") if isinstance(world.get("environment"), dict) else {}
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        try:
            local_danger = float(props.get("danger_level", 0.0))
        except (TypeError, ValueError):
            local_danger = 0.0
        try:
            world_danger = float(env.get("danger_level", 0.0))
        except (TypeError, ValueError):
            world_danger = 0.0
        return {
            "period": str(env.get("period") or "unknown"),
            "weather": str(env.get("weather") or env.get("weather_state") or "unknown"),
            "danger_level": max(local_danger, world_danger),
            "region_id": str(entity.get("region_id") or "unknown"),
        }

    def _need_values(self, entity: dict[str, Any]) -> dict[str, float]:
        if self.need_state_provider is not None:
            getter = getattr(self.need_state_provider, "get_needs", None)
            if callable(getter):
                provided = getter(str(entity.get("id") or ""))
                if isinstance(provided, dict):
                    values: dict[str, float] = {}
                    for name in self.DEFAULT_PRIORITIES:
                        try:
                            values[name] = min(1.0, max(0.0, float(provided.get(name, 0.0))))
                        except (TypeError, ValueError):
                            values[name] = 0.0
                    return values
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        raw = properties.get("needs") if isinstance(properties.get("needs"), dict) else {}
        values: dict[str, float] = {}
        for name in self.DEFAULT_PRIORITIES:
            try:
                values[name] = min(1.0, max(0.0, float(raw.get(name, 0.0))))
            except (TypeError, ValueError):
                values[name] = 0.0
        return values

    def _last_tick(self, npc_id: str, need: str) -> int | None:
        for row in reversed(self.history()):
            if row.get("npc_id") == npc_id and row.get("need") == need and row.get("status") == "scheduled":
                return int(row.get("tick", 0))
        return None

    def _candidate_targets(self, entity: dict[str, Any], need: str) -> list[str]:
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        values: list[str] = []
        plural = properties.get(self.TARGET_LIST_FIELDS[need])
        if isinstance(plural, list):
            values.extend(str(value).strip() for value in plural if str(value).strip())
        singular = str(properties.get(self.TARGET_FIELDS[need]) or "").strip()
        if singular:
            values.append(singular)
        return sorted({target_id for target_id in values if self._entity(target_id) is not None})

    def _select_target(self, entity: dict[str, Any], need: str, context: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]] | None]:
        candidates = self._candidate_targets(entity, need)
        if not candidates:
            return None, None
        npc_id = str(entity.get("id") or "")
        ranking: list[dict[str, Any]] | None = None
        selected: str | None = None
        if self.learning_provider is not None:
            chooser = getattr(self.learning_provider, "choose_target", None)
            ranker = getattr(self.learning_provider, "rank_targets", None)
            if callable(ranker):
                ranking = ranker(npc_id, need, candidates, context=context)
            if callable(chooser):
                candidate = chooser(npc_id, need, candidates, context=context)
                if candidate in candidates:
                    selected = str(candidate)
        if self.strategy_provider is not None and ranking:
            strategy_choose = getattr(self.strategy_provider, "choose", None)
            if callable(strategy_choose):
                strategy_selected, strategy_ranking = strategy_choose(actor_entity_id=npc_id, rankings=ranking, context=context)
                if strategy_selected in candidates:
                    selected = str(strategy_selected)
                    ranking = strategy_ranking
        if selected in candidates:
            return selected, ranking
        return candidates[0], ranking

    def _intent_for(self, entity: dict[str, Any], need: str, context: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, dict[str, Any] | None, list[dict[str, Any]] | None]:
        target_id, target_ranking = self._select_target(entity, need, context)
        if not target_id:
            return None, target_ranking, None, None
        base_intent = {
            "intent": "move_to_entity",
            "actor_entity_id": str(entity.get("id") or ""),
            "target_entity_id": target_id,
            "need": need,
            "learning_context": deepcopy(context),
        }
        if not self._composite_enabled() and self.compound_strategy_provider is not None:
            chooser = getattr(self.compound_strategy_provider, "choose", None)
            if callable(chooser):
                props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
                selected, strategy_ranking = chooser(
                    actor_entity_id=str(entity.get("id") or ""),
                    need=need,
                    target_entity_id=target_id,
                    actor_properties=props,
                    context=context,
                )
                if isinstance(selected, dict) and isinstance(selected.get("intent"), dict):
                    return deepcopy(selected["intent"]), target_ranking, deepcopy(selected), deepcopy(strategy_ranking)
        return base_intent, target_ranking, {"strategy_id": "direct", "strategy_kind": "direct"}, None

    def _composite_enabled(self) -> bool:
        return (
            self.composite_strategy_provider is not None
            and self.strategy_compiler is not None
            and self.strategy_executor is not None
        )

    @staticmethod
    def _predicted_satisfaction(target_ranking: list[dict[str, Any]] | None, target_id: str, fallback: float) -> float:
        for row in target_ranking or []:
            if str(row.get("target_entity_id") or "") != target_id:
                continue
            for field in ("effective_mean_satisfaction", "predicted_satisfaction", "mean_satisfaction"):
                try:
                    if row.get(field) is not None:
                        return min(1.0, max(0.0, float(row[field])))
                except (TypeError, ValueError):
                    pass
        return min(1.0, max(0.0, float(fallback)))

    @staticmethod
    def _strategy_shelters(entity: dict[str, Any]) -> list[str]:
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        values: list[str] = []
        plural = props.get("strategy_shelter_entity_ids")
        if isinstance(plural, list):
            values.extend(str(value).strip() for value in plural if str(value).strip())
        singular = str(props.get("strategy_shelter_entity_id") or "").strip()
        if singular:
            values.append(singular)
        return sorted(set(values))

    def _choose_composite(
        self,
        *,
        entity: dict[str, Any],
        need: str,
        target_id: str,
        context: dict[str, Any],
        target_ranking: list[dict[str, Any]] | None,
        severity: float,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, dict[str, Any] | None]:
        if not self._composite_enabled():
            return None, None, None
        generator = self.composite_strategy_provider
        candidates_fn = getattr(generator, "candidates", None)
        choose_fn = getattr(generator, "choose", None)
        compile_fn = getattr(self.strategy_compiler, "compile", None)
        if not callable(candidates_fn) or not callable(choose_fn) or not callable(compile_fn):
            return None, None, None
        props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        try:
            wait_ticks = max(0, int(props.get("strategy_wait_ticks", 3)))
        except (TypeError, ValueError):
            wait_ticks = 3
        candidates = candidates_fn(
            actor_entity_id=str(entity.get("id") or ""),
            target_entity_id=target_id,
            predicted_satisfaction=self._predicted_satisfaction(target_ranking, target_id, severity),
            context=deepcopy(context),
            shelter_entity_ids=self._strategy_shelters(entity),
            wait_ticks=wait_ticks,
        )
        selected, ranking = choose_fn(
            candidates,
            actor_entity_id=str(entity.get("id") or ""),
            need=need,
            target_entity_id=target_id,
            context=deepcopy(context),
        )
        if not isinstance(selected, dict):
            return None, deepcopy(ranking), None
        compiled = compile_fn(
            actor_entity_id=str(entity.get("id") or ""),
            need=need,
            target_entity_id=target_id,
            strategy=deepcopy(selected),
            context=deepcopy(context),
        )
        return deepcopy(selected), deepcopy(ranking), deepcopy(compiled)

    def evaluate_tick(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        results: list[dict[str, Any]] = []
        for npc_id in self.npc_ids:
            entity = self._entity(npc_id)
            if entity is None:
                continue
            values = self._need_values(entity)
            candidates = [(name, value, self.DEFAULT_PRIORITIES[name], value * self.DEFAULT_PRIORITIES[name]) for name, value in values.items() if value >= self.threshold]
            if not candidates:
                continue
            candidates.sort(key=lambda item: (-item[3], -item[2], item[0]))
            need, severity, priority, utility = candidates[0]
            last_tick = self._last_tick(npc_id, need)
            if last_tick is not None and tick - last_tick < self.cooldown_ticks:
                results.append({"npc_id": npc_id, "need": need, "status": "cooldown", "tick": tick})
                continue

            context = self._context_for(entity)
            intent, target_ranking, strategy, strategy_ranking = self._intent_for(entity, need, context)
            if intent is None:
                row = {
                    "need_schema": "npc_need_v6",
                    "npc_id": npc_id, "need": need, "severity": severity, "priority": priority,
                    "utility": utility, "tick": tick, "status": "no_target",
                    "learning_context": deepcopy(context), "target_ranking": target_ranking,
                    "strategy": strategy, "strategy_ranking": strategy_ranking,
                    "proposal_id": None, "plan_id": None, "strategy_execution_id": None,
                    "created_at_unix": time.time(),
                }
                self._append(row)
                results.append(row)
                continue

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

            strategy_id = str((strategy or {}).get("strategy_id") or "direct")
            goal_intent = {
                "intent": "move_to_entity",
                "actor_entity_id": npc_id,
                "target_entity_id": selected_target_id,
                "need": need,
                "learning_context": deepcopy(context),
                "strategy_id": strategy_id,
            }
            idem = f"npc-need:{npc_id}:{need}:{tick // max(1, self.cooldown_ticks or 1)}"
            proposal = self.proposals.propose(
                origin="npc_need",
                proposer_id=f"npc:{npc_id}",
                proposal_kind="agent_intent",
                payload={"intent": deepcopy(goal_intent)},
                metadata={
                    "need": need, "severity": severity, "utility": utility, "tick": tick,
                    "plan_priority": priority, "selected_target_entity_id": selected_target_id,
                    "learning_context": deepcopy(context), "target_ranking": deepcopy(target_ranking),
                    "strategy_id": strategy_id, "strategy": deepcopy(strategy),
                    "strategy_ranking": deepcopy(strategy_ranking),
                    "strategy_plan": deepcopy(composite_plan),
                },
                idempotency_key=idem,
            )
            if proposal.get("status") == "proposed":
                proposal = self.proposals.approve(
                    str(proposal["proposal_id"]),
                    decided_by=f"need_policy:{need}",
                    reason=f"deterministic need threshold reached: {severity:.3f}; utility={utility:.3f}; strategy={strategy_id}",
                )

            principal = {"source": "npc_need", "actor_id": npc_id, "authority": "entity_agent", "subject_entity_id": npc_id}
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
                "need_schema": "npc_need_v6",
                "npc_id": npc_id, "need": need, "severity": severity, "priority": priority,
                "utility": utility, "tick": tick, "status": "scheduled",
                "selected_target_entity_id": selected_target_id, "learning_context": deepcopy(context),
                "target_ranking": deepcopy(target_ranking), "strategy_id": strategy_id,
                "strategy": deepcopy(strategy), "strategy_ranking": deepcopy(strategy_ranking),
                "strategy_plan": deepcopy(composite_plan),
                "proposal_id": proposal.get("proposal_id"), "plan_id": plan_id,
                "strategy_execution_id": strategy_execution_id,
                "created_at_unix": time.time(),
            }
            self._append(row)
            results.append(row)
        return results
