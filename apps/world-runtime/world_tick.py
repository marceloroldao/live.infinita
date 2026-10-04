from __future__ import annotations

import inspect
import time
from typing import Any, Callable

from conditional_event_scheduler import ConditionalEventScheduler
from plan_arbiter import PlanArbiter
from plan_scheduler import PlanScheduler
from simulation_clock import SimulationClock
from world_event_scheduler import WorldEventScheduler


class WorldTickRunner:
    """Advance logical world time and evolve events plus active plans."""

    def __init__(
        self,
        clock: SimulationClock,
        scheduler: PlanScheduler,
        event_scheduler: WorldEventScheduler | None = None,
        conditional_event_scheduler: ConditionalEventScheduler | None = None,
        world_builder_agent: Any | None = None,
        plan_arbiter: PlanArbiter | None = None,
        npc_need_scheduler: Any | None = None,
        npc_idle_wander: Any | None = None,
        npc_need_dynamics: Any | None = None,
        npc_need_outcomes: Any | None = None,
        npc_social_evidence: Any | None = None,
        npc_social_exchange_producer: Any | None = None,
        npc_strategy_executor: Any | None = None,
        npc_composite_strategy_outcomes: Any | None = None,
        npc_causal_model: Any | None = None,
        stage_observer: Callable[[str, int], None] | None = None,
        monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.clock = clock
        self.scheduler = scheduler
        self.event_scheduler = event_scheduler
        self.conditional_event_scheduler = conditional_event_scheduler
        self.world_builder_agent = world_builder_agent
        self.npc_need_scheduler = npc_need_scheduler
        self.npc_idle_wander = npc_idle_wander
        self.npc_need_dynamics = npc_need_dynamics
        self.npc_need_outcomes = npc_need_outcomes
        self.npc_social_evidence = npc_social_evidence
        self.npc_social_exchange_producer = npc_social_exchange_producer
        self.npc_strategy_executor = npc_strategy_executor
        self.npc_composite_strategy_outcomes = npc_composite_strategy_outcomes
        self.npc_causal_model = npc_causal_model
        self.stage_observer = stage_observer
        self.monotonic_ns = monotonic_ns
        resume_evaluator = getattr(scheduler, "assess_resume", None)
        self.plan_arbiter = plan_arbiter or PlanArbiter(scheduler.ledger, resume_evaluator=resume_evaluator)

    @staticmethod
    def _idle_blocked_npc_ids(need_results: list[dict[str, Any]]) -> set[str]:
        """Block idle walking while need-driven work is scheduled or already running.

        `cooldown` is not active work; an already-running direct plan is detected by
        NpcIdleWander._has_active_plan(). `no_target` explicitly means the need
        could not produce a plan, so freezing the NPC would deadlock presentation
        forever when a target is absent. Idle movement may therefore continue
        until a real need plan becomes schedulable.
        """
        return {
            str(row.get("npc_id") or "")
            for row in need_results
            if str(row.get("npc_id") or "")
            and str(row.get("status") or "") in {"scheduled", "already_active"}
        }

    def _tick_plan(self, plan_id: str, logical_tick: int) -> dict[str, Any]:
        tick_fn = self.scheduler.tick
        try:
            parameters = inspect.signature(tick_fn).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "logical_tick" in parameters:
            return tick_fn(plan_id, logical_tick=logical_tick)
        return tick_fn(plan_id)

    def _causal_snapshot(self) -> dict[str, Any] | None:
        snapshot = getattr(self.npc_causal_model, "snapshot", None)
        if not callable(snapshot):
            return None
        value = snapshot()
        return value if isinstance(value, dict) else None

    def _stage(self, name: str, fn: Callable[[], Any]) -> Any:
        """Observe stage latency without changing authority or tick results."""
        if self.stage_observer is None:
            return fn()
        started = self.monotonic_ns()
        try:
            return fn()
        finally:
            try:
                self.stage_observer(name, max(0, self.monotonic_ns() - started))
            except Exception:
                # Optional observation never controls authoritative execution.
                pass

    def tick(self) -> dict[str, Any]:
        before = self.clock.state()
        if before.paused:
            return {
                "advanced": False,
                "clock": before.as_dict(),
                "events": [],
                "conditional_events": [],
                "world_builder": [],
                "causal_observations": [],
                "npc_need_dynamics": [],
                "npc_needs": [],
                "npc_idle_wander": [],
                "npc_strategies": [],
                "plan_replanning": [],
                "plan_arbitration": {
                    "preemptions": [],
                    "resumptions": [],
                    "replans": [],
                    "cancellations": [],
                },
                "plans": [],
                "npc_need_outcomes": [],
                "npc_social_evidence": [],
                "npc_social_exchanges": [],
                "npc_composite_strategy_outcomes": [],
            }

        after = self._stage("clock.advance", self.clock.advance)
        causal_before = self._stage("causal.snapshot_before", self._causal_snapshot)

        event_results: list[dict[str, Any]] = []
        if self.event_scheduler is not None:
            for row in self._stage("events.fire_due", lambda: self.event_scheduler.fire_due(after.tick)):
                event_results.append({
                    "scheduled_event_id": row.get("scheduled_event_id"),
                    "status": row.get("status"),
                    "due_tick": row.get("due_tick"),
                    "fire_count": row.get("fire_count"),
                    "last_world_event_id": row.get("last_world_event_id"),
                    "last_mutation_decision_id": row.get("last_mutation_decision_id"),
                })

        conditional_results: list[dict[str, Any]] = []
        if self.conditional_event_scheduler is not None:
            for row in self._stage("conditional_events.evaluate", lambda: self.conditional_event_scheduler.evaluate_tick(after.tick)):
                conditional_results.append({
                    "conditional_event_id": row.get("conditional_event_id"),
                    "effect_kind": row.get("effect_kind"),
                    "status": row.get("status"),
                    "condition_value": row.get("last_condition_value"),
                    "fire_count": row.get("fire_count"),
                    "last_fired_tick": row.get("last_fired_tick"),
                    "last_world_event_id": row.get("last_world_event_id"),
                    "last_mutation_decision_id": row.get("last_mutation_decision_id"),
                    "last_proposal_id": row.get("last_proposal_id"),
                    "last_plan_id": row.get("last_plan_id"),
                })

        causal_results: list[dict[str, Any]] = []
        if self.npc_causal_model is not None and causal_before is not None:
            causal_after = self._stage("causal.snapshot_after", self._causal_snapshot)
            observer = getattr(self.npc_causal_model, "observe_environment_transition", None)
            if callable(observer) and causal_after is not None:
                relation = self._stage(
                    "causal.observe",
                    lambda: observer(
                        observation_id=f"world-tick:{after.tick}",
                        logical_tick=after.tick,
                        before=causal_before,
                        after=causal_after,
                        source_events=event_results + conditional_results,
                    ),
                )
                if isinstance(relation, dict):
                    causal_results.append({
                        "hypothesis_type": relation.get("hypothesis_type"),
                        "cause": relation.get("cause"),
                        "effect": relation.get("effect"),
                        "count": relation.get("count"),
                        "support_count": relation.get("support_count"),
                        "counter_count": relation.get("counter_count"),
                        "neutral_count": relation.get("neutral_count"),
                        "mean_effect_delta": relation.get("mean_effect_delta"),
                        "confidence": relation.get("confidence"),
                        "status": relation.get("status"),
                    })

        need_dynamics_results: list[dict[str, Any]] = []
        if self.npc_need_dynamics is not None:
            for row in self._stage("npc_need_dynamics.advance", lambda: self.npc_need_dynamics.advance_tick(after.tick)):
                need_dynamics_results.append({
                    "npc_id": row.get("npc_id"),
                    "tick": row.get("tick"),
                    "before": row.get("before"),
                    "after": row.get("after"),
                })

        need_results: list[dict[str, Any]] = []
        if self.npc_need_scheduler is not None:
            for row in self._stage("npc_needs.evaluate", lambda: self.npc_need_scheduler.evaluate_tick(after.tick)):
                need_results.append({
                    "npc_id": row.get("npc_id"),
                    "need": row.get("need"),
                    "severity": row.get("severity"),
                    "priority": row.get("priority"),
                    "utility": row.get("utility"),
                    "status": row.get("status"),
                    "proposal_id": row.get("proposal_id"),
                    "plan_id": row.get("plan_id"),
                    "strategy_execution_id": row.get("strategy_execution_id"),
                })

        idle_results: list[dict[str, Any]] = []
        if self.npc_idle_wander is not None:
            blocked_npcs = self._idle_blocked_npc_ids(need_results)
            for row in self._stage("npc_idle_wander.evaluate", lambda: self.npc_idle_wander.evaluate_tick(after.tick, blocked_npc_ids=blocked_npcs)):
                idle_results.append({
                    "npc_id": row.get("npc_id"),
                    "tick": row.get("tick"),
                    "status": row.get("status"),
                    "plan_id": row.get("plan_id"),
                    "region_id": row.get("region_id"),
                    "position": row.get("position"),
                    "priority": row.get("priority"),
                    "environmental_context": row.get("environmental_context"),
                })

        strategy_results: list[dict[str, Any]] = []
        if self.npc_strategy_executor is not None:
            for row in self._stage("npc_strategies.tick_all", lambda: self.npc_strategy_executor.tick_all(logical_tick=after.tick)):
                strategy_results.append({
                    "strategy_execution_id": row.get("strategy_execution_id"),
                    "strategy_id": (row.get("strategy_plan") or {}).get("strategy_id") if isinstance(row.get("strategy_plan"), dict) else None,
                    "status": row.get("status"),
                    "phase_index": row.get("phase_index"),
                    "child_plan_id": row.get("child_plan_id"),
                    "wait_started_tick": row.get("wait_started_tick"),
                    "last_error": row.get("last_error"),
                })

        replan_results: list[dict[str, Any]] = []
        replan_all = getattr(self.scheduler, "replan_all", None)
        if callable(replan_all):
            for row in self._stage("plans.replan_all", replan_all):
                replan_results.append({
                    "plan_id": row.get("plan_id"),
                    "status": row.get("status"),
                    "plan_revision": row.get("plan_revision", 0),
                    "next_step_index": row.get("next_step_index", 0),
                    "last_error": row.get("last_error"),
                })

        arbitration = self._stage("plans.arbitrate", self.plan_arbiter.reconcile)
        results: list[dict[str, Any]] = []
        for record in arbitration.get("runnable", []):
            plan_id = str(record.get("plan_id") or "").strip()
            if not plan_id:
                continue
            result = self._stage("plans.tick", lambda: self._tick_plan(plan_id, after.tick))
            results.append({
                "plan_id": plan_id,
                "actor_entity_id": result.get("actor_entity_id"),
                "priority": result.get("priority", 0),
                "plan_revision": result.get("plan_revision", 0),
                "status": result.get("status"),
                "next_step_index": result.get("next_step_index"),
                "started_logical_tick": result.get("started_logical_tick"),
                "completed_logical_tick": result.get("completed_logical_tick"),
                "preemption_count": result.get("preemption_count", 0),
                "replan_count": result.get("replan_count", 0),
                "last_world_event_id": result.get("last_world_event_id"),
                "last_mutation_decision_id": result.get("last_mutation_decision_id"),
            })

        outcome_results: list[dict[str, Any]] = []
        full_need_outcomes: list[dict[str, Any]] = []
        if self.npc_need_outcomes is not None:
            for row in self._stage("npc_need_outcomes.process", self.npc_need_outcomes.process_completed):
                full_need_outcomes.append(row)
                outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
                outcome_results.append({
                    "plan_id": row.get("plan_id"),
                    "proposal_id": row.get("proposal_id"),
                    "npc_id": row.get("npc_id"),
                    "need": row.get("need"),
                    "status": row.get("status"),
                    "before": outcome.get("before"),
                    "after": outcome.get("after"),
                    "amount": outcome.get("amount"),
                    "strategy_experience": row.get("strategy_experience"),
                })

        social_evidence_results: list[dict[str, Any]] = []
        if self.npc_social_evidence is not None:
            for row in self._stage(
                "npc_social_evidence.observe_encounters",
                lambda: self.npc_social_evidence.observe_encounters(full_need_outcomes),
            ):
                social_evidence_results.append({
                    "evidence_id": row.get("evidence_id"),
                    "npc_id": row.get("npc_id"),
                    "peer_entity_id": row.get("peer_entity_id"),
                    "kind": row.get("kind"),
                    "status": row.get("status"),
                    "confirmed": row.get("confirmed"),
                    "satisfaction_delta": row.get("satisfaction_delta"),
                })

        social_exchange_results: list[dict[str, Any]] = []
        if self.npc_social_exchange_producer is not None:
            for row in self._stage("npc_social_exchange.reconcile", self.npc_social_exchange_producer.reconcile):
                social_exchange_results.append({
                    "evidence_id": row.get("evidence_id"),
                    "npc_id": row.get("npc_id"),
                    "peer_entity_id": row.get("peer_entity_id"),
                    "status": row.get("status"),
                    "confirmed": row.get("confirmed"),
                    "satisfaction_delta": row.get("satisfaction_delta"),
                })

        composite_outcome_results: list[dict[str, Any]] = []
        if self.npc_composite_strategy_outcomes is not None:
            for row in self._stage("npc_composite_outcomes.process", self.npc_composite_strategy_outcomes.process_completed):
                composite_outcome_results.append({
                    "strategy_execution_id": row.get("strategy_execution_id"),
                    "strategy_id": row.get("strategy_id"),
                    "terminal_plan_id": row.get("terminal_plan_id"),
                    "npc_id": row.get("npc_id"),
                    "need": row.get("need"),
                    "target_entity_id": row.get("target_entity_id"),
                    "satisfaction": row.get("satisfaction"),
                    "elapsed_ticks": row.get("elapsed_ticks"),
                    "preemptions": row.get("preemptions"),
                    "replans": row.get("replans"),
                    "observed_risk": row.get("observed_risk"),
                })

        world_builder_results: list[dict[str, Any]] = []
        if self.world_builder_agent is not None:
            for row in self._stage(
                "world_builder.evaluate",
                lambda: self.world_builder_agent.evaluate_tick(after.tick),
            ):
                world_builder_results.append({
                    "tick": row.get("tick"),
                    "status": row.get("status"),
                    "entity_id": row.get("entity_id"),
                    "entity_type": row.get("entity_type"),
                    "region_id": row.get("region_id"),
                    "role": row.get("role"),
                    "projection_id": row.get("projection_id"),
                    "world_event_id": row.get("world_event_id"),
                    "mutation_decision_id": row.get("mutation_decision_id"),
                    "reason": row.get("reason"),
                })

        return {
            "advanced": True,
            "clock": after.as_dict(),
            "events": event_results,
            "conditional_events": conditional_results,
            "world_builder": world_builder_results,
            "causal_observations": causal_results,
            "npc_need_dynamics": need_dynamics_results,
            "npc_needs": need_results,
            "npc_idle_wander": idle_results,
            "npc_strategies": strategy_results,
            "plan_replanning": replan_results,
            "plan_arbitration": {
                "preemptions": arbitration.get("preemptions", []),
                "resumptions": arbitration.get("resumptions", []),
                "replans": arbitration.get("replans", []),
                "cancellations": arbitration.get("cancellations", []),
            },
            "plans": results,
            "npc_need_outcomes": outcome_results,
            "npc_social_evidence": social_evidence_results,
            "npc_social_exchanges": social_exchange_results,
            "npc_composite_strategy_outcomes": composite_outcome_results,
        }
