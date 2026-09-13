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

    def __init__(
        self,
        path: Path,
        proposal_ledger: ProposalLedger,
        plan_scheduler: PlanScheduler,
        *,
        npc_ids: list[str],
        threshold: float = 0.70,
        cooldown_ticks: int = 20,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.proposals = proposal_ledger
        self.plans = plan_scheduler
        self.npc_ids = tuple(sorted({str(v).strip() for v in npc_ids if str(v).strip()}))
        self.threshold = float(threshold)
        self.cooldown_ticks = max(0, int(cooldown_ticks))

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

    @staticmethod
    def _need_values(entity: dict[str, Any]) -> dict[str, float]:
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        raw = properties.get("needs") if isinstance(properties.get("needs"), dict) else {}
        values: dict[str, float] = {}
        for name in NpcNeedScheduler.DEFAULT_PRIORITIES:
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

    def _intent_for(self, entity: dict[str, Any], need: str) -> dict[str, Any] | None:
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        target_field = self.TARGET_FIELDS[need]
        target_id = str(properties.get(target_field) or "").strip()
        if not target_id or self._entity(target_id) is None:
            return None
        return {
            "intent": "move_to_entity",
            "actor_entity_id": str(entity.get("id") or ""),
            "target_entity_id": target_id,
            "need": need,
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
                (name, value, self.DEFAULT_PRIORITIES[name])
                for name, value in values.items()
                if value >= self.threshold
            ]
            if not candidates:
                continue
            # Deterministic winner: severity first, then policy priority, then name.
            candidates.sort(key=lambda item: (-item[1], -item[2], item[0]))
            need, severity, priority = candidates[0]
            last_tick = self._last_tick(npc_id, need)
            if last_tick is not None and tick - last_tick < self.cooldown_ticks:
                results.append({"npc_id": npc_id, "need": need, "status": "cooldown", "tick": tick})
                continue

            intent = self._intent_for(entity, need)
            if intent is None:
                row = {
                    "need_schema": "npc_need_v1",
                    "npc_id": npc_id,
                    "need": need,
                    "severity": severity,
                    "priority": priority,
                    "tick": tick,
                    "status": "no_target",
                    "proposal_id": None,
                    "plan_id": None,
                    "created_at_unix": time.time(),
                }
                self._append(row)
                results.append(row)
                continue

            idem = f"npc-need:{npc_id}:{need}:{tick // max(1, self.cooldown_ticks or 1)}"
            proposal = self.proposals.propose(
                origin="npc_need",
                proposer_id=f"npc:{npc_id}",
                proposal_kind="agent_intent",
                payload={"intent": deepcopy(intent)},
                metadata={"need": need, "severity": severity, "tick": tick, "plan_priority": priority},
                idempotency_key=idem,
            )
            if proposal.get("status") == "proposed":
                proposal = self.proposals.approve(
                    str(proposal["proposal_id"]),
                    decided_by=f"need_policy:{need}",
                    reason=f"deterministic need threshold reached: {severity:.3f}",
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
                "need_schema": "npc_need_v1",
                "npc_id": npc_id,
                "need": need,
                "severity": severity,
                "priority": priority,
                "tick": tick,
                "status": "scheduled",
                "proposal_id": proposal.get("proposal_id"),
                "plan_id": plan.get("plan_id"),
                "created_at_unix": time.time(),
            }
            self._append(row)
            results.append(row)
        return results
