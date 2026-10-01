from __future__ import annotations

from copy import deepcopy
import time
from typing import Any, Callable

from packages.spatial import (
    AgentIntentResolver,
    DeterministicIntentPlanner,
    IntentPlan,
    MutationPrincipal,
    PlanStep,
)
from mutation_gate_service import GuardedMutationService
from plan_ledger import PlanLedger


class PlanScheduler:
    """Execute at most one authoritative plan step per tick."""

    def __init__(
        self,
        ledger: PlanLedger,
        planner: DeterministicIntentPlanner,
        resolver: AgentIntentResolver,
        guarded_mutations: GuardedMutationService,
        proposal_ledger: Any | None = None,
        stage_observer: Callable[[str, int], None] | None = None,
        monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.ledger = ledger
        self.planner = planner
        self.resolver = resolver
        self.guarded = guarded_mutations
        self.proposal_ledger = proposal_ledger
        self.stage_observer = stage_observer
        self.monotonic_ns = monotonic_ns

    def _stage(self, name: str, fn: Callable[[], Any]) -> Any:
        if self.stage_observer is None:
            return fn()
        started = self.monotonic_ns()
        try:
            return fn()
        finally:
            try:
                self.stage_observer(
                    name,
                    max(0, self.monotonic_ns() - started),
                )
            except Exception:
                # Profiling is observational only.
                pass

    @staticmethod
    def _principal(value: dict[str, Any]) -> MutationPrincipal:
        return MutationPrincipal.from_dict(value)

    @staticmethod
    def _rehydrate_plan(value: dict[str, Any]) -> IntentPlan:
        steps: list[PlanStep] = []
        for raw in value.get("steps", []):
            steps.append(PlanStep(
                int(raw["step_index"]),
                str(raw["kind"]),
                deepcopy(raw["intent"]),
                raw.get("expected_region_id"),
                raw.get("goal_region_id"),
            ))
        return IntentPlan(
            str(value.get("intent_type") or ""),
            value.get("actor_entity_id"),
            value.get("source_region_id"),
            value.get("goal_region_id"),
            tuple(str(v) for v in value.get("region_path", [])),
            tuple(steps),
        )

    def _entity_label(self, entity_id: str | None, fallback: str) -> str:
        value = str(entity_id or "").strip()
        if not value:
            return fallback
        entity = self.resolver.store.get_entity(value)
        if not isinstance(entity, dict):
            return fallback
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        label = str(properties.get("label") or "").strip()
        return label or fallback

    def _public_narration(self, plan: IntentPlan, step: PlanStep) -> str:
        """Narration is presentation text; plan ids/revisions belong only in audit context."""
        intent = dict(step.intent or {})
        intent_type = str(intent.get("intent") or intent.get("type") or plan.intent_type or "").strip().lower()
        actor = self._entity_label(plan.actor_entity_id, "Nov")

        if intent_type == "move_to_entity":
            target = self._entity_label(str(intent.get("target_entity_id") or ""), "seu próximo destino")
            return f"{actor} segue pelo caminho até {target}."
        if intent_type == "move_to_position":
            return f"{actor} continua avançando pelo caminho."
        if intent_type == "establish_relation":
            target = self._entity_label(str(intent.get("target_entity_id") or ""), "algo próximo")
            return f"{actor} se aproxima de {target} e interage com ele."
        if intent_type == "clear_relation":
            target = self._entity_label(str(intent.get("target_entity_id") or ""), "o que estava observando")
            return f"{actor} se afasta de {target} e segue adiante."
        if intent_type == "set_environment":
            return "O ambiente ao redor de Nov começa a mudar."
        if intent_type == "transfer_possession":
            return f"{actor} reorganiza um objeto que encontrou pelo caminho."
        return f"{actor} continua sua jornada pelo mundo."

    def schedule(
        self,
        *,
        intent: dict[str, Any],
        principal: MutationPrincipal | dict[str, Any],
        proposer_id: str,
        proposal_id: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> dict[str, Any]:
        if isinstance(principal, MutationPrincipal):
            principal_dict = {
                "source": principal.source,
                "actor_id": principal.actor_id,
                "authority": principal.authority,
                "subject_entity_id": principal.subject_entity_id,
            }
        else:
            principal_dict = dict(principal)
            MutationPrincipal.from_dict(principal_dict)
        plan = self._stage(
            "plan.schedule.plan",
            lambda: self.planner.plan(intent),
        )
        return self._stage(
            "plan.schedule.ledger_create",
            lambda: self.ledger.create(
                proposal_id=proposal_id,
                proposer_id=proposer_id,
                principal=principal_dict,
                intent=intent,
                plan=plan.as_dict(),
                idempotency_key=idempotency_key,
                priority=int(priority),
                actor_entity_id=plan.actor_entity_id,
            ),
        )

    def execute_ephemeral_one_step(
        self,
        *,
        intent: dict[str, Any],
        principal: MutationPrincipal | dict[str, Any],
        logical_tick: int | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
    ) -> dict[str, Any]:
        # Narrow fail-closed path for regenerable one-step actions.
        if isinstance(principal, MutationPrincipal):
            principal_obj = principal
            principal_dict = {
                "source": principal.source,
                "actor_id": principal.actor_id,
                "authority": principal.authority,
                "subject_entity_id": principal.subject_entity_id,
            }
        else:
            principal_dict = dict(principal)
            principal_obj = MutationPrincipal.from_dict(principal_dict)

        plan = self._stage(
            "plan.ephemeral.plan",
            lambda: self.planner.plan(intent),
        )
        if len(plan.steps) != 1:
            return {
                "ok": False,
                "status": "requires_persistent",
                "reason": "ephemeral execution requires exactly one step",
                "step_count": len(plan.steps),
            }

        step = self._stage(
            "plan.ephemeral.revalidate",
            lambda: self.planner.revalidate_step(plan, 0),
        )
        resolved = self._stage(
            "plan.ephemeral.resolve",
            lambda: self.resolver.resolve(step.intent),
        )
        narration = self._stage(
            "plan.ephemeral.narration",
            lambda: self._public_narration(plan, step),
        )
        context = {
            "ephemeral": True,
            "idempotency_key": str(idempotency_key or "").strip() or None,
            "plan_priority": int(priority),
            "logical_tick": int(logical_tick) if logical_tick is not None else None,
            "intent_plan": {
                "intent_type": plan.intent_type,
                "step_index": 0,
                "total_steps": 1,
                "step_kind": step.kind,
                "goal_region_id": plan.goal_region_id,
                "region_path": list(plan.region_path),
            },
        }
        result = self._stage(
            "plan.ephemeral.guarded_commit",
            lambda: self.guarded.commit(
                list(resolved.operations),
                principal=principal_obj,
                context=context,
                narration=narration,
            ),
        )
        audit = result.get("audit") if isinstance(result, dict) else {}
        event = result.get("event") if isinstance(result, dict) else {}
        world = result.get("world") if isinstance(result, dict) else {}
        return {
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "status": "completed" if isinstance(result, dict) and result.get("ok") else "failed",
            "mutation_decision_id": str((audit or {}).get("mutation_decision_id") or "").strip() or None,
            "world_event_id": str((event or {}).get("event_id") or "").strip() or None,
            "state_hash": str((world or {}).get("state_hash") or "").strip() or None,
            "reason": (
                str(((result or {}).get("decision") or {}).get("reason") or "").strip()
                if isinstance(result, dict) else "ephemeral execution failed"
            ),
            "principal": principal_dict,
        }

    def assess_resume(self, record: dict[str, Any]) -> dict[str, str]:
        try:
            plan = self._rehydrate_plan(dict(record.get("plan") or {}))
            index = int(record.get("next_step_index", 0))
            if index >= len(plan.steps):
                return {"action": "resume", "reason": "plan already at terminal cursor"}
            original_intent = dict(record.get("intent") or {})
            try:
                fresh = self.planner.plan(original_intent)
            except ValueError as exc:
                return {"action": "cancel", "reason": f"goal invalid after preemption: {exc}"}
            try:
                self.planner.revalidate_step(plan, index)
            except ValueError as exc:
                return {"action": "replan", "reason": str(exc)}
            if plan.goal_region_id != fresh.goal_region_id:
                return {
                    "action": "replan",
                    "reason": f"goal region changed: {plan.goal_region_id!r} -> {fresh.goal_region_id!r}",
                }
            return {"action": "resume", "reason": "goal and current step remain valid"}
        except Exception as exc:
            return {"action": "cancel", "reason": f"resume validation failed: {exc}"}

    def _reject_proposal(self, record: dict[str, Any], reason: str) -> None:
        if self.proposal_ledger is None:
            return
        proposal_id = str(record.get("proposal_id") or "").strip()
        if not proposal_id:
            return
        proposal = self.proposal_ledger.get(proposal_id)
        if proposal is not None and proposal.get("status") == "approved":
            self.proposal_ledger.reject(proposal_id, decided_by="plan_scheduler", reason=reason)

    def _commit_proposal_if_complete(self, record: dict[str, Any]) -> None:
        if self.proposal_ledger is None or record.get("status") != "completed":
            return
        proposal_id = str(record.get("proposal_id") or "").strip()
        if not proposal_id:
            return
        proposal = self.proposal_ledger.get(proposal_id)
        if proposal is None or proposal.get("status") != "approved":
            return
        completed = list(record.get("completed_steps") or [])
        if not completed:
            return
        last = completed[-1]
        decision_id = str(last.get("mutation_decision_id") or "").strip()
        event_id = str(last.get("world_event_id") or "").strip()
        if decision_id and event_id:
            self.proposal_ledger.commit(
                proposal_id,
                decided_by="plan_scheduler",
                mutation_decision_id=decision_id,
                world_event_id=event_id,
            )

    def replan(self, plan_id: str) -> dict[str, Any]:
        record = self.ledger.get(plan_id)
        if record is None:
            raise KeyError("plan not found")
        if str(record.get("status") or "") != "replanning":
            return record
        reason = str(record.get("last_error") or "world state invalidated current plan")
        try:
            fresh = self.planner.plan(dict(record.get("intent") or {}))
        except ValueError as exc:
            cancelled = self.ledger.transition(
                plan_id,
                "cancelled",
                waiting_reason=None,
                preempted_by_plan_id=None,
                last_error=f"replan failed: {exc}",
            )
            self._reject_proposal(cancelled, str(cancelled.get("last_error") or exc))
            return cancelled
        return self.ledger.replace_plan_revision(plan_id, plan=fresh.as_dict(), reason=reason)

    def replan_all(self) -> list[dict[str, Any]]:
        rows = sorted(
            [row for row in self.ledger.active() if str(row.get("status") or "") == "replanning"],
            key=lambda row: str(row.get("plan_id") or ""),
        )
        return [self.replan(str(row["plan_id"])) for row in rows]

    def tick(self, plan_id: str, logical_tick: int | None = None) -> dict[str, Any]:
        record = self._stage(
            "plan.tick.lookup",
            lambda: self.ledger.get(plan_id),
        )
        if record is None:
            raise KeyError("plan not found")
        status = str(record.get("status") or "")
        if status in self.ledger.TERMINAL:
            self._stage(
                "plan.tick.proposal_commit",
                lambda: self._commit_proposal_if_complete(record),
            )
            return record
        if status == "waiting":
            return record
        if status == "replanning":
            record = self._stage(
                "plan.tick.replan",
                lambda: self.replan(plan_id),
            )
            if str(record.get("status") or "") in self.ledger.TERMINAL:
                return record
        if str(record.get("status") or "") == "planned":
            updates: dict[str, Any] = {}
            if logical_tick is not None and record.get("started_logical_tick") is None:
                updates["started_logical_tick"] = int(logical_tick)
            record = self._stage(
                "plan.tick.transition_running",
                lambda: self.ledger.transition(plan_id, "running", **updates),
            )

        plan = self._stage(
            "plan.tick.rehydrate",
            lambda: self._rehydrate_plan(record["plan"]),
        )
        index = int(record.get("next_step_index", 0))
        if index >= len(plan.steps):
            updates = {"completed_logical_tick": int(logical_tick)} if logical_tick is not None else {}
            record = self._stage(
                "plan.tick.transition_completed",
                lambda: self.ledger.transition(plan_id, "completed", **updates),
            )
            self._stage(
                "plan.tick.proposal_commit",
                lambda: self._commit_proposal_if_complete(record),
            )
            return record

        try:
            step = self._stage(
                "plan.tick.revalidate",
                lambda: self.planner.revalidate_step(plan, index),
            )
        except ValueError as exc:
            return self._stage(
                "plan.tick.transition_replanning",
                lambda: self.ledger.transition(
                    plan_id,
                    "replanning",
                    last_error=str(exc),
                ),
            )

        try:
            resolved = self._stage(
                "plan.tick.resolve",
                lambda: self.resolver.resolve(step.intent),
            )
        except ValueError as exc:
            failed = self._stage(
                "plan.tick.transition_failed",
                lambda: self.ledger.transition(
                    plan_id,
                    "failed",
                    last_error=str(exc),
                ),
            )
            self._stage(
                "plan.tick.proposal_reject",
                lambda: self._reject_proposal(failed, str(exc)),
            )
            return failed

        principal = self._stage(
            "plan.tick.principal",
            lambda: self._principal(record["principal"]),
        )
        narration = self._stage(
            "plan.tick.narration",
            lambda: self._public_narration(plan, step),
        )
        context = {
            "plan_id": plan_id,
            "proposal_id": record.get("proposal_id"),
            "plan_priority": int(record.get("priority", 0)),
            "plan_revision": int(record.get("plan_revision", 0)),
            "logical_tick": int(logical_tick) if logical_tick is not None else None,
            "intent_plan": {
                "intent_type": plan.intent_type,
                "step_index": index,
                "total_steps": len(plan.steps),
                "step_kind": step.kind,
                "goal_region_id": plan.goal_region_id,
                "region_path": list(plan.region_path),
            },
        }
        result = self._stage(
            "plan.tick.guarded_commit",
            lambda: self.guarded.commit(
                list(resolved.operations),
                principal=principal,
                context=context,
                narration=narration,
            ),
        )
        audit = result.get("audit") or {}
        decision_id = str(
            audit.get("mutation_decision_id") or ""
        ).strip() or None
        if not result.get("ok"):
            reason = str(
                (result.get("decision") or {}).get("reason")
                or "mutation rejected"
            )
            failed = self._stage(
                "plan.tick.transition_failed",
                lambda: self.ledger.transition(
                    plan_id,
                    "failed",
                    last_error=reason,
                    last_mutation_decision_id=decision_id,
                ),
            )
            self._stage(
                "plan.tick.proposal_reject",
                lambda: self._reject_proposal(failed, reason),
            )
            return failed

        event = result.get("event") or {}
        world = result.get("world") or {}
        event_id = str(event.get("event_id") or "").strip() or None
        state_hash = str(world.get("state_hash") or "").strip() or None
        updated = self._stage(
            "plan.tick.mark_step_completed",
            lambda: self.ledger.mark_step_completed(
                plan_id,
                step_index=index,
                mutation_decision_id=decision_id,
                world_event_id=event_id,
                state_hash=state_hash,
                logical_tick=logical_tick,
            ),
        )
        self._stage(
            "plan.tick.proposal_commit",
            lambda: self._commit_proposal_if_complete(updated),
        )
        return updated

    def tick_all(self, logical_tick: int | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for record in self.ledger.active():
            results.append(self.tick(str(record["plan_id"]), logical_tick=logical_tick))
        return results
