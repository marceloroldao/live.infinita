from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcCompositeStrategyOutcomeProcessor:
    """Learn exactly once from completed composite strategy executions.

    A composite strategy is eligible only after its terminal movement child has a
    need outcome. Intermediate waypoints and waiting phases never create success
    evidence on their own. Concrete episodes are persisted separately from the
    statistical strategy aggregates when an episodic-memory provider is supplied.
    """

    def __init__(
        self,
        path: Path,
        strategy_executor: Any,
        plan_ledger: Any,
        need_outcomes: Any,
        strategy_experience_provider: Any,
        episodic_memory_provider: Any | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.strategy_executor = strategy_executor
        self.plan_ledger = plan_ledger
        self.need_outcomes = need_outcomes
        self.strategy_experience_provider = strategy_experience_provider
        self.episodic_memory_provider = episodic_memory_provider
        self._processed_cache: set[str] | None = None
        self._processed_signature: tuple[int, int, int, int] | None = None

    def _signature(self) -> tuple[int, int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

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
        before = self._signature()
        cached = self._processed_cache is not None and self._processed_signature == before
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(payload)
        except BaseException:
            self._processed_cache = None
            raise
        after = self._signature()
        expected_size = (before[2] if before else 0) + len(payload.encode("utf-8"))
        if cached and after is not None and after[2] == expected_size and (
            before is None or before[:2] == after[:2]
        ):
            execution_id = str(row.get("strategy_execution_id") or "")
            if execution_id:
                assert self._processed_cache is not None
                self._processed_cache.add(execution_id)
            self._processed_signature = after
        else:
            self._processed_cache = None
        return row

    def _processed(self) -> set[str]:
        if self._processed_cache is not None and self._processed_signature == self._signature():
            return self._processed_cache
        for _ in range(3):
            before = self._signature()
            processed = {
                str(row.get("strategy_execution_id") or "")
                for row in self.history()
                if row.get("strategy_execution_id")
            }
            after = self._signature()
            if before == after:
                self._processed_cache = processed
                self._processed_signature = after
                return processed
        raise RuntimeError("composite outcome ledger changed while indexing processed IDs")

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
        get_applied = getattr(self.need_outcomes, "get_applied", None)
        if callable(get_applied):
            value = get_applied(plan_id)
            return value if isinstance(value, dict) else None
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
        unprocessed = getattr(self.strategy_executor, "unprocessed_completed", None)
        current = getattr(self.strategy_executor, "current", None)
        observer = getattr(self.strategy_experience_provider, "observe_strategy", None)
        if not callable(unprocessed) and not callable(current):
            return []
        if not callable(observer):
            return []

        remember = getattr(self.episodic_memory_provider, "remember", None)
        results: list[dict[str, Any]] = []
        # The persistent audit index is the exactly-once guard. The strategy
        # executor returns only not-yet-audited completions when supported.
        rows = unprocessed(processed) if callable(unprocessed) else current()
        for execution in rows:
            if not isinstance(execution, dict) or execution.get("status") != "completed":
                continue
            execution_id = str(execution.get("strategy_execution_id") or "").strip()
            if not execution_id or execution_id in processed:
                continue
            terminal_plan_id = self._terminal_plan_id(execution)
            if not terminal_plan_id:
                continue
            terminal_plan = self._plan(terminal_plan_id) or {}
            terminal_intent = terminal_plan.get("intent") if isinstance(terminal_plan.get("intent"), dict) else {}
            if terminal_intent.get("target_evidence_source") == "observed_social_capability":
                # Arrival at a social-capable actor is not yet an interaction or
                # a learned success. Mark the composite terminal exactly once.
                row = {
                    "strategy_execution_id": execution_id,
                    "terminal_plan_id": terminal_plan_id,
                    "status": "social_goal_no_reward",
                    "learning": None,
                    "episode_id": None,
                }
                self._append(row)
                processed.add(execution_id)
                results.append(row)
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

            npc_id = str(plan.get("actor_entity_id") or execution.get("principal", {}).get("actor_id") or "")
            need = str(plan.get("need") or outcome_row.get("need") or "")
            target_entity_id = str(plan.get("target_entity_id") or outcome_row.get("target_entity_id") or "")
            strategy_id = str(plan.get("strategy_id") or "direct")
            learned = observer(
                outcome_id=f"composite:{execution_id}",
                npc_id=npc_id,
                need=need,
                target_entity_id=target_entity_id,
                strategy_id=strategy_id,
                context=deepcopy(context),
                satisfaction=satisfaction,
                elapsed_ticks=elapsed,
                preemptions=preemptions,
                replans=replans,
                observed_risk=risk,
                strategy_execution_id=execution_id,
                terminal_plan_id=terminal_plan_id,
            )

            terminal_plan = self._plan(terminal_plan_id) or {}
            logical_tick = terminal_plan.get("completed_logical_tick")
            episode = None
            if callable(remember):
                episode = remember(
                    episode_id=f"strategy:{execution_id}",
                    npc_id=npc_id,
                    logical_tick=int(logical_tick) if logical_tick is not None else None,
                    need=need,
                    target_entity_id=target_entity_id,
                    strategy_id=strategy_id,
                    context=deepcopy(context),
                    satisfaction=satisfaction,
                    elapsed_ticks=elapsed,
                    preemptions=preemptions,
                    replans=replans,
                    observed_risk=risk,
                    source={
                        "kind": "composite_strategy_outcome",
                        "strategy_execution_id": execution_id,
                        "terminal_plan_id": terminal_plan_id,
                        "proposal_id": outcome_row.get("proposal_id"),
                    },
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
                "episode_id": episode.get("episode_id") if isinstance(episode, dict) else None,
            }
            self._append(audit)
            processed.add(execution_id)
            results.append(audit)
        return results
