from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcCompositeStrategyOutcomeProcessor:
    """Learn exactly once from completed composite strategy executions.

    A composite strategy is eligible only after its terminal movement child has a
    need outcome. Intermediate waypoints and waiting phases never create success
    evidence on their own.
    """

    def __init__(
        self,
        path: Path,
        strategy_executor: Any,
        plan_ledger: Any,
        need_outcomes: Any,
        strategy_experience_provider: Any,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.strategy_executor = strategy_executor
        self.plan_ledger = plan_ledger
        self.need_outcomes = need_outcomes
        self.strategy_experience_provider = strategy_experience_provider

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

    def _processed(self) -> set[str]:
        return {
            str(row.get("strategy_execution_id") or "")
            for row in self.history()
            if row.get("strategy_execution_id")
        }

    @staticmethod
    def _terminal_plan_id(execution: dict[str, Any]) -> str | None:
        completed = execution.get("completed_phases") if isinstance(execution.get("completed_phases"), list) else []
        for row in reversed(completed):
            if not isinstance(row, dict) or row.get("kind") != "move_to_entity":
                continue
            plan_id = str(row.get("child_plan_id") or "").strip()
            if plan_id:
                return plan_id
        return None

    def _need_outcome(self, plan_id: str) -> dict[str, Any] | None:
        history = getattr(self.need_outcomes, "history", None)
        if not callable(history):
            return None
        for row in reversed(history()):
            if isinstance(row, dict) and str(row.get("plan_id") or "") == plan_id and row.get("status") == "applied":
                return row
        return None

    def _plan(self, plan_id: str) -> dict[str, Any] | None:
        getter = getattr(self.plan_ledger, "get", None)
        value = getter(plan_id) if callable(getter) else None
        return value if isinstance(value, dict) else None

    def _execution_metrics(self, execution: dict[str, Any]) -> tuple[int, int, int]:
        completed = execution.get("completed_phases") if isinstance(execution.get("completed_phases"), list) else []
        start_ticks: list[int] = []
        end_ticks: list[int] = []
        preemptions = 0
        replans = 0
        for phase in completed:
            if not isinstance(phase, dict):
                continue
            if phase.get("kind") == "wait_ticks":
                if phase.get("wait_started_tick") is not None:
                    start_ticks.append(int(phase["wait_started_tick"]))
                if phase.get("completed_logical_tick") is not None:
                    end_ticks.append(int(phase["completed_logical_tick"]))
                continue
            plan_id = str(phase.get("child_plan_id") or "").strip()
            plan = self._plan(plan_id) if plan_id else None
            if plan is None:
                continue
            if plan.get("started_logical_tick") is not None:
                start_ticks.append(int(plan["started_logical_tick"]))
            if plan.get("completed_logical_tick") is not None:
                end_ticks.append(int(plan["completed_logical_tick"]))
            preemptions += max(0, int(plan.get("preemption_count", 0)))
            replans += max(0, int(plan.get("replan_count", 0)))
        if not start_ticks or not end_ticks:
            return 0, preemptions, replans
        return max(1, max(end_ticks) - min(start_ticks) + 1), preemptions, replans

    def process_completed(self) -> list[dict[str, Any]]:
        processed = self._processed()
        current = getattr(self.strategy_executor, "current", None)
        observer = getattr(self.strategy_experience_provider, "observe_strategy", None)
        if not callable(current) or not callable(observer):
            return []

        results: list[dict[str, Any]] = []
        for execution in current():
            if not isinstance(execution, dict) or execution.get("status") != "completed":
                continue
            execution_id = str(execution.get("strategy_execution_id") or "").strip()
            if not execution_id or execution_id in processed:
                continue
            terminal_plan_id = self._terminal_plan_id(execution)
            if not terminal_plan_id:
                continue
            outcome_row = self._need_outcome(terminal_plan_id)
            if outcome_row is None:
                continue

            plan = execution.get("strategy_plan") if isinstance(execution.get("strategy_plan"), dict) else {}
            outcome = outcome_row.get("outcome") if isinstance(outcome_row.get("outcome"), dict) else {}
            before = float(outcome.get("before", 0.0))
            after = float(outcome.get("after", before))
            satisfaction = min(1.0, max(0.0, before - after))
            elapsed, preemptions, replans = self._execution_metrics(execution)
            context = plan.get("context") if isinstance(plan.get("context"), dict) else {}
            try:
                risk = min(1.0, max(0.0, float(context.get("danger_level", 0.0))))
            except (TypeError, ValueError):
                risk = 0.0

            learned = observer(
                outcome_id=f"composite:{execution_id}",
                npc_id=str(plan.get("actor_entity_id") or execution.get("principal", {}).get("actor_id") or ""),
                need=str(plan.get("need") or outcome_row.get("need") or ""),
                target_entity_id=str(plan.get("target_entity_id") or outcome_row.get("target_entity_id") or ""),
                strategy_id=str(plan.get("strategy_id") or "direct"),
                context=deepcopy(context),
                satisfaction=satisfaction,
                elapsed_ticks=elapsed,
                preemptions=preemptions,
                replans=replans,
                observed_risk=risk,
                strategy_execution_id=execution_id,
                terminal_plan_id=terminal_plan_id,
            )
            audit = {
                "composite_strategy_outcome_schema": "npc_composite_strategy_outcome_v1",
                "strategy_execution_id": execution_id,
                "strategy_id": plan.get("strategy_id"),
                "terminal_plan_id": terminal_plan_id,
                "npc_id": plan.get("actor_entity_id"),
                "need": plan.get("need"),
                "target_entity_id": plan.get("target_entity_id"),
                "satisfaction": satisfaction,
                "elapsed_ticks": elapsed,
                "preemptions": preemptions,
                "replans": replans,
                "observed_risk": risk,
                "learning": deepcopy(learned),
            }
            self._append(audit)
            processed.add(execution_id)
            results.append(audit)
        return results
