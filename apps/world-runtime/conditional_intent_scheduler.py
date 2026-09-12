from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from conditional_event_scheduler import ConditionalEventScheduler
from plan_scheduler import PlanScheduler
from proposal_ledger import ProposalLedger
from packages.spatial import MutationPrincipal


class ConditionalIntentError(ValueError):
    pass


class ConditionalIntentScheduler:
    """Turn deterministic world conditions into approved persistent plans.

    The trigger does not mutate world state. It creates an agent_intent proposal,
    records deterministic approval, then creates a PlanLedger entry through the
    existing PlanScheduler. Every later plan step still passes MutationGate.
    """

    TERMINAL = frozenset({"completed", "cancelled", "failed"})

    def __init__(
        self,
        path: Path,
        condition_evaluator: ConditionalEventScheduler,
        proposal_ledger: ProposalLedger,
        plan_scheduler: PlanScheduler,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conditions = condition_evaluator
        self.proposals = proposal_ledger
        self.plans = plan_scheduler

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

    def current(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in self.history():
            trigger_id = str(row.get("conditional_intent_id") or "").strip()
            if not trigger_id:
                continue
            if trigger_id not in latest:
                order.append(trigger_id)
            latest[trigger_id] = row
        return [latest[trigger_id] for trigger_id in order]

    def get(self, conditional_intent_id: str) -> dict[str, Any] | None:
        return next((row for row in self.current() if row.get("conditional_intent_id") == conditional_intent_id), None)

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    @staticmethod
    def _principal_dict(principal: MutationPrincipal | dict[str, Any]) -> dict[str, Any]:
        if isinstance(principal, MutationPrincipal):
            return {
                "source": principal.source,
                "actor_id": principal.actor_id,
                "authority": principal.authority,
                "subject_entity_id": principal.subject_entity_id,
            }
        result = dict(principal)
        MutationPrincipal.from_dict(result)
        return result

    def register(
        self,
        *,
        condition: dict[str, Any],
        intent: dict[str, Any],
        principal: MutationPrincipal | dict[str, Any],
        proposer_id: str,
        approved_by: str,
        trigger_mode: str = "edge",
        cooldown_ticks: int = 0,
        one_shot: bool = False,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self.conditions._validate_condition(condition)
        # Validate intent/plan shape now, without scheduling it.
        self.plans.planner.plan(intent)
        trigger_mode = str(trigger_mode or "edge").strip().lower()
        if trigger_mode not in {"edge", "level"}:
            raise ConditionalIntentError("trigger_mode must be edge or level")
        if int(cooldown_ticks) < 0:
            raise ConditionalIntentError("cooldown_ticks must be >= 0")
        proposer_id = str(proposer_id or "").strip()
        approved_by = str(approved_by or "").strip()
        if not proposer_id or not approved_by:
            raise ConditionalIntentError("proposer_id and approved_by are required")
        principal_dict = self._principal_dict(principal)

        key = str(idempotency_key or "").strip() or None
        if key:
            for row in self.current():
                if row.get("idempotency_key") == key:
                    return row

        now = time.time()
        row = {
            "conditional_intent_schema": "conditional_intent_v1",
            "conditional_intent_id": f"cint_{int(now * 1000)}_{uuid.uuid4().hex[:10]}",
            "status": "active",
            "condition": deepcopy(condition),
            "intent": deepcopy(intent),
            "principal": principal_dict,
            "proposer_id": proposer_id,
            "approved_by": approved_by,
            "trigger_mode": trigger_mode,
            "cooldown_ticks": int(cooldown_ticks),
            "one_shot": bool(one_shot),
            "metadata": deepcopy(metadata or {}),
            "idempotency_key": key,
            "last_raw_condition_value": False,
            "last_condition_value": False,
            "true_since_tick": None,
            "last_evaluated_tick": None,
            "last_fired_tick": None,
            "fire_count": 0,
            "last_proposal_id": None,
            "last_plan_id": None,
            "last_error": None,
            "created_at_unix": now,
            "updated_at_unix": now,
        }
        return self._append(row)

    def cancel(self, conditional_intent_id: str, *, reason: str = "cancelled") -> dict[str, Any]:
        row = self.get(conditional_intent_id)
        if row is None:
            raise KeyError("conditional intent not found")
        if row.get("status") in self.TERMINAL:
            return row
        updated = deepcopy(row)
        updated["status"] = "cancelled"
        updated["last_error"] = str(reason)[:1000]
        updated["updated_at_unix"] = time.time()
        return self._append(updated)

    def evaluate_tick(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        results: list[dict[str, Any]] = []
        active = sorted(
            [row for row in self.current() if row.get("status") == "active"],
            key=lambda row: str(row.get("conditional_intent_id") or ""),
        )
        for row in active:
            updated = deepcopy(row)
            try:
                raw_value = self.conditions.evaluate_condition(dict(row.get("condition") or {}))
                value, true_since = self.conditions._sustained_value(row, raw_value, tick)
            except Exception as exc:
                updated["status"] = "failed"
                updated["last_error"] = str(exc)[:1000]
                updated["last_evaluated_tick"] = tick
                updated["updated_at_unix"] = time.time()
                self._append(updated)
                results.append(updated)
                continue

            previous = bool(row.get("last_condition_value", False))
            last_fired = row.get("last_fired_tick")
            cooldown = int(row.get("cooldown_ticks", 0))
            cooldown_ok = last_fired is None or tick - int(last_fired) >= cooldown
            mode = str(row.get("trigger_mode") or "edge")
            should_fire = value and cooldown_ok and (mode == "level" or not previous)

            updated["last_raw_condition_value"] = raw_value
            updated["last_condition_value"] = value
            updated["true_since_tick"] = true_since
            updated["last_evaluated_tick"] = tick
            updated["updated_at_unix"] = time.time()

            if should_fire:
                trigger_id = str(row.get("conditional_intent_id") or "")
                fire_ordinal = int(row.get("fire_count", 0)) + 1
                proposal = self.proposals.propose(
                    origin="conditional_world",
                    proposer_id=str(row.get("proposer_id") or "world"),
                    proposal_kind="agent_intent",
                    payload={"intent": deepcopy(row.get("intent") or {})},
                    metadata={
                        **deepcopy(row.get("metadata") or {}),
                        "conditional_intent_id": trigger_id,
                        "fired_at_tick": tick,
                    },
                    idempotency_key=f"{trigger_id}:fire:{fire_ordinal}:proposal",
                )
                proposal_id = str(proposal["proposal_id"])
                current_proposal = self.proposals.get(proposal_id) or proposal
                if current_proposal.get("status") == "proposed":
                    self.proposals.approve(
                        proposal_id,
                        decided_by=str(row.get("approved_by") or "system"),
                        reason="deterministic conditional intent trigger",
                    )
                plan = self.plans.schedule(
                    intent=deepcopy(row.get("intent") or {}),
                    principal=dict(row.get("principal") or {}),
                    proposer_id=str(row.get("proposer_id") or "world"),
                    proposal_id=proposal_id,
                    idempotency_key=f"{trigger_id}:fire:{fire_ordinal}:plan",
                )
                updated["fire_count"] = fire_ordinal
                updated["last_fired_tick"] = tick
                updated["last_proposal_id"] = proposal_id
                updated["last_plan_id"] = str(plan.get("plan_id") or "") or None
                updated["last_error"] = None
                if bool(row.get("one_shot")):
                    updated["status"] = "completed"

            self._append(updated)
            results.append(updated)
        return results
