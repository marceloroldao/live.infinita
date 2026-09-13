from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from plan_scheduler import PlanScheduler
from proposal_ledger import ProposalLedger


class NpcNeedScheduler:
    """Turn bounded NPC internal needs into semantic intent proposals.

    This component never mutates world state directly. It reads explicit NPC ids,
    scores configured needs, emits at most one dominant need per NPC per tick,
    records the decision append-only, and schedules the resulting semantic intent.
    Every plan step still passes through the normal Mutation Gate.
    """

    DEFAULT_PRIORITIES = {
        "safety": 1000,
        "energy": 700,
        "social": 400,
        "curiosity": 200,
    }

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

    def _select_target(
        self,
        entity: dict[str, Any],
        need: str,
        context: dict[str, Any],
    ) -> tuple[str | None, list[dict[str, Any]] | None]:
        candidates = self._candidate_targets(entity, need)
        if not candidates:
            return None, None
        npc_id = str(entity.get("id") or "")
        if self.learning_provider is not None:
            chooser = getattr(self.learning_provider, "choose_target", None)
            ranker = getattr(self.learning_provider, "rank_targets", None)
            if callable(chooser):
                selected = chooser(npc_id, need, candidates, context=context)
                ranking = ranker(npc_id, need, candidates, context=context) if callable(ranker) else None
                if selected in candidates:
                    return str(selected), ranking
        return candidates[0], None

    def _intent_for(
        self,
        entity: dict[str, Any],
        need: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None]:
        target_id, ranking = self._select_target(entity, need, context)
        if not target_id:
            return None, ranking
        return {
            "intent": "move_to_entity",
            "actor_entity_id": str(entity.get("id") or ""),
            "target_entity_id": target_id,
            "need": need,
            "learning_context": deepcopy(context),
        }, ranking

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
            need, severity, priority, utility = candidates[0]
            last_tick = self._last_tick(npc_id, need)
            if last_tick is not None and tick - last_tick < self.cooldown_ticks:
                results.append({"npc_id": npc_id, "need": need, "status": "cooldown", "tick": tick})
                continue

            context = self._context_for(entity)
            intent, target_ranking = self._intent_for(entity, need, context)
            if intent is None:
                row = {
                    "need_schema": "npc_need_v3",
                    "npc_id": npc_id,
                    "need": need,
                    "severity": severity,
                    "priority": priority,
                    "utility": utility,
                    "tick": tick,
                    "status": "no_target",
                    "learning_context": deepcopy(context),
                    "target_ranking": target_ranking,
                    "proposal_id": None,
                    "plan_id": None,
                    "created_at_unix": time.time(),
                }
                self._append(row)
                results.append(row)
                continue

            selected_target_id = str(intent.get("target_entity_id") or "")
            idem = f"npc-need:{npc_id}:{need}:{tick // max(1, self.cooldown_ticks or 1)}"
            proposal = self.proposals.propose(
                origin="npc_need",
                proposer_id=f"npc:{npc_id}",
                proposal_kind="agent_intent",
                payload={"intent": deepcopy(intent)},
                metadata={
                    "need": need,
                    "severity": severity,
                    "utility": utility,
                    "tick": tick,
                    "plan_priority": priority,
                    "selected_target_entity_id": selected_target_id,
                    "learning_context": deepcopy(context),
                    "target_ranking": deepcopy(target_ranking),
                },
                idempotency_key=idem,
            )
            if proposal.get("status") == "proposed":
                proposal = self.proposals.approve(
                    str(proposal["proposal_id"]),
                    decided_by=f"need_policy:{need}",
                    reason=f"deterministic need threshold reached: {severity:.3f}; utility={utility:.3f}",
                )
            plan = self.plans.schedule(
                intent=deepcopy(intent),
                principal={
                    "source": "npc_need",
                    "actor_id": npc_id,
                    "authority": "entity_agent",
                    "subject_entity_id": npc_id,
                },
                proposer_id=f"npc:{npc_id}",
                proposal_id=str(proposal["proposal_id"]),
                idempotency_key=f"npc-need-plan:{proposal['proposal_id']}",
                priority=priority,
            )
            row = {
                "need_schema": "npc_need_v3",
                "npc_id": npc_id,
                "need": need,
                "severity": severity,
                "priority": priority,
                "utility": utility,
                "tick": tick,
                "status": "scheduled",
                "selected_target_entity_id": selected_target_id,
                "learning_context": deepcopy(context),
                "target_ranking": deepcopy(target_ranking),
                "proposal_id": proposal.get("proposal_id"),
                "plan_id": plan.get("plan_id"),
                "created_at_unix": time.time(),
            }
            self._append(row)
            results.append(row)
        return results
