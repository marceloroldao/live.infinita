from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any


class PlanLedgerError(ValueError):
    pass


class PlanLedger:
    """Append-only lifecycle ledger for persistent deterministic plans."""

    TERMINAL = frozenset({"completed", "failed", "cancelled"})
    ALLOWED = {
        "planned": frozenset({"running", "cancelled", "failed"}),
        "running": frozenset({"running", "waiting", "replanning", "completed", "failed", "cancelled"}),
        "waiting": frozenset({"running", "replanning", "failed", "cancelled"}),
        "replanning": frozenset({"running", "failed", "cancelled"}),
        "completed": frozenset(),
        "failed": frozenset(),
        "cancelled": frozenset(),
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

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
            plan_id = str(row.get("plan_id") or "").strip()
            if not plan_id:
                continue
            if plan_id not in latest:
                order.append(plan_id)
            latest[plan_id] = row
        return [latest[plan_id] for plan_id in order]

    def get(self, plan_id: str) -> dict[str, Any] | None:
        plan_id = str(plan_id or "").strip()
        return next((row for row in self.current() if row.get("plan_id") == plan_id), None)

    def active(self) -> list[dict[str, Any]]:
        return [row for row in self.current() if row.get("status") not in self.TERMINAL]

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def create(
        self,
        *,
        proposal_id: str | None,
        proposer_id: str,
        principal: dict[str, Any],
        intent: dict[str, Any],
        plan: dict[str, Any],
        idempotency_key: str | None = None,
        priority: int = 0,
        actor_entity_id: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            for row in self.current():
                if row.get("idempotency_key") == idempotency_key:
                    return row
        now = time.time()
        actor = str(actor_entity_id or intent.get("actor_entity_id") or principal.get("subject_entity_id") or "").strip() or None
        row = {
            "plan_schema": "intent_plan_v4",
            "plan_id": f"plan_{int(now * 1000)}_{uuid.uuid4().hex[:10]}",
            "proposal_id": str(proposal_id or "").strip() or None,
            "proposer_id": str(proposer_id or "").strip(),
            "principal": deepcopy(principal),
            "intent": deepcopy(intent),
            "plan": deepcopy(plan),
            "plan_revision": 0,
            "plan_revision_history": [],
            "priority": int(priority),
            "actor_entity_id": actor,
            "status": "planned",
            "next_step_index": 0,
            "completed_steps": [],
            "waiting_reason": None,
            "preempted_by_plan_id": None,
            "preemption_count": 0,
            "replan_count": 0,
            "started_logical_tick": None,
            "completed_logical_tick": None,
            "idempotency_key": str(idempotency_key or "").strip() or None,
            "last_error": None,
            "created_at_unix": now,
            "updated_at_unix": now,
        }
        if not row["proposer_id"]:
            raise PlanLedgerError("proposer_id is required")
        return self._append(row)

    def transition(self, plan_id: str, status: str, **updates: Any) -> dict[str, Any]:
        current = self.get(plan_id)
        if current is None:
            raise KeyError("plan not found")
        old = str(current.get("status") or "")
        status = str(status or "").strip().lower()
        if status not in self.ALLOWED.get(old, frozenset()):
            raise PlanLedgerError(f"invalid transition: {old} -> {status}")
        row = deepcopy(current)
        row["status"] = status
        for key, value in updates.items():
            row[key] = deepcopy(value)
        row["updated_at_unix"] = time.time()
        return self._append(row)

    def replace_plan_revision(self, plan_id: str, *, plan: dict[str, Any], reason: str) -> dict[str, Any]:
        current = self.get(plan_id)
        if current is None:
            raise KeyError("plan not found")
        if str(current.get("status") or "") != "replanning":
            raise PlanLedgerError("plan replacement requires replanning status")

        revision = int(current.get("plan_revision", 0))
        history = list(current.get("plan_revision_history") or [])
        history.append({
            "plan_revision": revision,
            "plan": deepcopy(current.get("plan") or {}),
            "next_step_index": int(current.get("next_step_index", 0)),
            "reason": str(reason or "replanned"),
            "replaced_at_unix": time.time(),
        })
        return self.transition(
            plan_id,
            "running",
            plan=deepcopy(plan),
            plan_revision=revision + 1,
            plan_revision_history=history,
            replan_count=int(current.get("replan_count", 0)) + 1,
            next_step_index=0,
            waiting_reason=None,
            preempted_by_plan_id=None,
            last_error=None,
        )

    def mark_step_completed(
        self,
        plan_id: str,
        *,
        step_index: int,
        mutation_decision_id: str | None,
        world_event_id: str | None,
        state_hash: str | None,
        logical_tick: int | None = None,
    ) -> dict[str, Any]:
        current = self.get(plan_id)
        if current is None:
            raise KeyError("plan not found")
        expected = int(current.get("next_step_index", 0))
        if step_index != expected:
            raise PlanLedgerError(f"step out of order: {step_index} != {expected}")
        completed = list(current.get("completed_steps") or [])
        step_row = {
            "plan_revision": int(current.get("plan_revision", 0)),
            "step_index": step_index,
            "mutation_decision_id": mutation_decision_id,
            "world_event_id": world_event_id,
            "state_hash": state_hash,
        }
        if logical_tick is not None:
            step_row["logical_tick"] = int(logical_tick)
        completed.append(step_row)
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        next_index = step_index + 1
        status = "completed" if next_index >= len(steps) else "running"
        updates: dict[str, Any] = {
            "next_step_index": next_index,
            "completed_steps": completed,
            "waiting_reason": None,
            "preempted_by_plan_id": None,
            "last_error": None,
        }
        if current.get("started_logical_tick") is None and logical_tick is not None:
            updates["started_logical_tick"] = int(logical_tick)
        if status == "completed" and logical_tick is not None:
            updates["completed_logical_tick"] = int(logical_tick)
        return self.transition(plan_id, status, **updates)
