from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcStrategyExecutionError(ValueError):
    pass


class NpcStrategyExecutor:
    """Persist and execute one semantic phase of a composite NPC strategy per tick.

    Movement phases are delegated to the normal PlanScheduler, so all existing
    planning, arbitration, revalidation and Mutation Gate rules remain in force.
    wait_ticks phases use only the logical tick supplied by WorldTick.
    """

    TERMINAL = frozenset({"completed", "failed", "cancelled"})

    def __init__(self, path: Path, plan_scheduler: Any) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_scheduler = plan_scheduler
        self._view_by_id: dict[str, dict[str, Any]] | None = None
        self._view_order: list[str] = []
        self._view_idempotency: dict[str, str] = {}
        self._view_signature: tuple[int, int, int, int] | None = None

    def _signature(self) -> tuple[int, int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def _ensure_view(self) -> None:
        if self._view_by_id is not None and self._view_signature == self._signature():
            return
        # Rebuild from the durable JSONL after restart or external modification.
        for _ in range(3):
            before = self._signature()
            latest: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for row in self._history():
                execution_id = str(row.get("strategy_execution_id") or "").strip()
                if not execution_id:
                    continue
                if execution_id not in latest:
                    order.append(execution_id)
                latest[execution_id] = row
            after = self._signature()
            if before == after:
                idempotency: dict[str, str] = {}
                for execution_id in order:
                    key = str(latest[execution_id].get("idempotency_key") or "")
                    if key:
                        idempotency.setdefault(key, execution_id)
                self._view_by_id = latest
                self._view_order = order
                self._view_idempotency = idempotency
                self._view_signature = after
                return
        raise NpcStrategyExecutionError("strategy ledger changed during replay")

    def _history(self) -> list[dict[str, Any]]:
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
        before = self._signature()
        cached = self._view_by_id is not None and self._view_signature == before
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(payload)
        except BaseException:
            self._view_by_id = None
            raise
        after = self._signature()
        expected_size = (before[2] if before else 0) + len(payload.encode("utf-8"))
        if cached and after is not None and after[2] == expected_size and (
            before is None or after[:2] == before[:2]
        ):
            assert self._view_by_id is not None
            execution_id = str(row.get("strategy_execution_id") or "").strip()
            if execution_id:
                previous = self._view_by_id.get(execution_id)
                previous_key = str(previous.get("idempotency_key") or "") if previous else ""
                key = str(row.get("idempotency_key") or "")
                if previous is not None and previous_key != key:
                    self._view_by_id = None
                else:
                    if previous is None:
                        self._view_order.append(execution_id)
                    self._view_by_id[execution_id] = deepcopy(row)
                    if key:
                        self._view_idempotency.setdefault(key, execution_id)
            self._view_signature = after
        else:
            self._view_by_id = None
        return row

    def current(self) -> list[dict[str, Any]]:
        self._ensure_view()
        assert self._view_by_id is not None
        return [deepcopy(self._view_by_id[key]) for key in self._view_order]

    def completed_unprocessed(self, processed_ids: set[str]) -> list[dict[str, Any]]:
        """Return only completed, not-yet-audited executions in creation order."""
        self._ensure_view()
        assert self._view_by_id is not None
        return [
            deepcopy(row)
            for execution_id in self._view_order
            if execution_id not in processed_ids
            for row in (self._view_by_id[execution_id],)
            if row.get("status") == "completed"
        ]

    def find_active_need(self, npc_id: str, need: str) -> dict[str, Any] | None:
        """Find earliest in-flight goal without copying all historical executions."""
        self._ensure_view()
        assert self._view_by_id is not None
        npc_id, need = str(npc_id or ""), str(need or "")
        for execution_id in self._view_order:
            row = self._view_by_id[execution_id]
            if str(row.get("status") or "") in self.TERMINAL:
                continue
            plan = row.get("strategy_plan")
            if not isinstance(plan, dict):
                continue
            if str(plan.get("actor_entity_id") or "") == npc_id and str(plan.get("need") or "") == need:
                return deepcopy(row)
        return None

    def get(self, execution_id: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        row = self._view_by_id.get(str(execution_id or "").strip())
        return deepcopy(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        execution_id = self._view_idempotency.get(str(key or ""))
        row = self._view_by_id.get(execution_id) if execution_id else None
        return deepcopy(row) if row is not None else None

    def start(
        self,
        strategy_plan: dict[str, Any],
        *,
        principal: dict[str, Any],
        proposer_id: str,
        proposal_id: str | None = None,
        priority: int = 0,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        phases = strategy_plan.get("phases") if isinstance(strategy_plan.get("phases"), list) else []
        if not phases:
            raise NpcStrategyExecutionError("strategy plan requires phases")
        if idempotency_key:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
        now = time.time()
        row = {
            "strategy_execution_schema": "npc_strategy_execution_v2",
            "strategy_execution_id": f"strategy_exec_{int(now * 1000)}_{uuid.uuid4().hex[:10]}",
            "strategy_plan": deepcopy(strategy_plan),
            "principal": deepcopy(principal),
            "proposer_id": str(proposer_id or "").strip(),
            "proposal_id": str(proposal_id or "").strip() or None,
            "priority": int(priority),
            "status": "running",
            "phase_index": 0,
            "child_plan_id": None,
            "wait_started_tick": None,
            "completed_phases": [],
            "last_error": None,
            "idempotency_key": str(idempotency_key or "").strip() or None,
            "created_at_unix": now,
            "updated_at_unix": now,
        }
        if not row["proposer_id"]:
            raise NpcStrategyExecutionError("proposer_id is required")
        return self._append(row)

    def _update(self, row: dict[str, Any], **changes: Any) -> dict[str, Any]:
        updated = deepcopy(row)
        for key, value in changes.items():
            updated[key] = deepcopy(value)
        updated["updated_at_unix"] = time.time()
        return self._append(updated)

    @staticmethod
    def _phase(record: dict[str, Any]) -> dict[str, Any] | None:
        strategy_plan = record.get("strategy_plan") if isinstance(record.get("strategy_plan"), dict) else {}
        phases = strategy_plan.get("phases") if isinstance(strategy_plan.get("phases"), list) else []
        index = int(record.get("phase_index", 0))
        return deepcopy(phases[index]) if 0 <= index < len(phases) else None

    def _complete_phase(self, record: dict[str, Any], *, logical_tick: int, details: dict[str, Any]) -> dict[str, Any]:
        completed = list(record.get("completed_phases") or [])
        completed.append({
            "phase_index": int(record.get("phase_index", 0)),
            "completed_logical_tick": int(logical_tick),
            **deepcopy(details),
        })
        strategy_plan = record.get("strategy_plan") if isinstance(record.get("strategy_plan"), dict) else {}
        phases = strategy_plan.get("phases") if isinstance(strategy_plan.get("phases"), list) else []
        next_index = int(record.get("phase_index", 0)) + 1
        status = "completed" if next_index >= len(phases) else "running"
        return self._update(
            record,
            status=status,
            phase_index=next_index,
            child_plan_id=None,
            wait_started_tick=None,
            completed_phases=completed,
            last_error=None,
        )

    def tick(self, execution_id: str, *, logical_tick: int) -> dict[str, Any]:
        record = self.get(execution_id)
        if record is None:
            raise KeyError("strategy execution not found")
        if str(record.get("status") or "") in self.TERMINAL:
            return record

        phase = self._phase(record)
        if phase is None:
            return self._update(record, status="failed", last_error="phase cursor out of range")
        kind = str(phase.get("kind") or "").strip().lower()
        intent = phase.get("intent") if isinstance(phase.get("intent"), dict) else {}

        if kind == "wait_ticks":
            ticks = max(1, int(intent.get("ticks", 0)))
            started = record.get("wait_started_tick")
            if started is None:
                return self._update(record, wait_started_tick=int(logical_tick))
            elapsed = int(logical_tick) - int(started)
            if elapsed < ticks:
                return record
            return self._complete_phase(
                record,
                logical_tick=logical_tick,
                details={"kind": "wait_ticks", "wait_ticks": ticks, "wait_started_tick": int(started)},
            )

        if kind != "move_to_entity":
            return self._update(record, status="failed", last_error=f"unsupported phase kind: {kind}")

        child_plan_id = str(record.get("child_plan_id") or "").strip()
        if not child_plan_id:
            # The originating proposal belongs to the whole composite strategy.
            # Only the terminal/outcome-eligible child receives it, so an
            # intermediate waypoint cannot commit the proposal prematurely.
            child_proposal_id = None
            if intent.get("need_outcome_eligible") is True:
                child_proposal_id = str(record.get("proposal_id") or "").strip() or None
            child = self.plan_scheduler.schedule(
                intent=deepcopy(intent),
                principal=deepcopy(record.get("principal") or {}),
                proposer_id=str(record.get("proposer_id") or "strategy_executor"),
                proposal_id=child_proposal_id,
                idempotency_key=f"strategy-phase:{execution_id}:{int(record.get('phase_index', 0))}",
                priority=int(record.get("priority", 0)),
            )
            child_plan_id = str(child.get("plan_id") or "").strip()
            if not child_plan_id:
                return self._update(record, status="failed", last_error="child plan was not created")
            return self._update(record, child_plan_id=child_plan_id)

        ledger = getattr(self.plan_scheduler, "ledger", None)
        getter = getattr(ledger, "get", None)
        child = getter(child_plan_id) if callable(getter) else None
        if not isinstance(child, dict):
            return self._update(record, status="failed", last_error=f"child plan missing: {child_plan_id}")
        child_status = str(child.get("status") or "")
        if child_status == "completed":
            return self._complete_phase(
                record,
                logical_tick=logical_tick,
                details={"kind": "move_to_entity", "child_plan_id": child_plan_id},
            )
        if child_status in {"failed", "cancelled"}:
            return self._update(
                record,
                status="failed",
                last_error=f"child plan {child_plan_id} ended as {child_status}",
            )
        return record

    def tick_all(self, *, logical_tick: int) -> list[dict[str, Any]]:
        rows = sorted(
            [row for row in self.current() if str(row.get("status") or "") not in self.TERMINAL],
            key=lambda row: str(row.get("strategy_execution_id") or ""),
        )
        return [self.tick(str(row["strategy_execution_id"]), logical_tick=logical_tick) for row in rows]
