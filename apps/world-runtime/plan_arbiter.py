from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Callable

from plan_ledger import PlanLedger


class PlanArbiter:
    """Deterministic per-actor priority arbiter for persistent plans.

    At most one executable plan per actor is runnable. Higher priority wins;
    ties are resolved by creation time then plan_id. Preempted plans are kept in
    `waiting`. Before resumption, an optional resume evaluator may classify the
    plan as resume, replan, or cancel.
    """

    def __init__(
        self,
        ledger: PlanLedger,
        resume_evaluator: Callable[[dict[str, Any]], dict[str, str]] | None = None,
    ) -> None:
        self.ledger = ledger
        self.resume_evaluator = resume_evaluator

    @staticmethod
    def actor_id(record: dict[str, Any]) -> str:
        explicit = str(record.get("actor_entity_id") or "").strip()
        if explicit:
            return explicit
        intent = record.get("intent") if isinstance(record.get("intent"), dict) else {}
        actor = str(intent.get("actor_entity_id") or "").strip()
        if actor:
            return actor
        principal = record.get("principal") if isinstance(record.get("principal"), dict) else {}
        return str(principal.get("subject_entity_id") or principal.get("actor_id") or "").strip()

    @staticmethod
    def _priority(record: dict[str, Any]) -> int:
        try:
            return int(record.get("priority", 0))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _rank(cls, record: dict[str, Any]) -> tuple[int, float, str]:
        return (-cls._priority(record), float(record.get("created_at_unix", 0.0)), str(record.get("plan_id") or ""))

    @staticmethod
    def _participates(record: dict[str, Any]) -> bool:
        status = str(record.get("status") or "")
        if status in {"planned", "running"}:
            return True
        return status == "waiting" and str(record.get("waiting_reason") or "") == "preempted"

    def _resume_decision(self, record: dict[str, Any]) -> dict[str, str]:
        if self.resume_evaluator is None:
            return {"action": "resume", "reason": "no resume evaluator configured"}
        try:
            result = dict(self.resume_evaluator(deepcopy(record)) or {})
        except Exception as exc:
            return {"action": "cancel", "reason": f"resume evaluator failed: {exc}"}
        action = str(result.get("action") or "").strip().lower()
        if action not in {"resume", "replan", "cancel"}:
            return {"action": "cancel", "reason": f"invalid resume action: {action!r}"}
        return {"action": action, "reason": str(result.get("reason") or action)}

    def reconcile(self) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        unowned: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for record in self.ledger.active():
            if not self._participates(record):
                blocked.append(record)
                continue
            actor = self.actor_id(record)
            if actor:
                groups[actor].append(record)
            else:
                unowned.append(record)

        runnable: list[dict[str, Any]] = []
        preemptions: list[dict[str, Any]] = []
        resumptions: list[dict[str, Any]] = []
        replans: list[dict[str, Any]] = []
        cancellations: list[dict[str, Any]] = []

        for actor in sorted(groups):
            rows = sorted(groups[actor], key=self._rank)
            winner: dict[str, Any] | None = None

            for candidate in rows:
                status = str(candidate.get("status") or "")
                candidate_id = str(candidate.get("plan_id") or "")
                if status != "waiting":
                    winner = candidate
                    break

                decision = self._resume_decision(candidate)
                action = decision["action"]
                reason = decision["reason"]
                if action == "resume":
                    winner = self.ledger.transition(
                        candidate_id,
                        "running",
                        waiting_reason=None,
                        preempted_by_plan_id=None,
                        last_error=None,
                        resume_decision="resume",
                        resume_reason=reason,
                    )
                    resumptions.append({
                        "actor_entity_id": actor,
                        "plan_id": candidate_id,
                        "decision": "resume",
                        "reason": reason,
                    })
                    break
                if action == "replan":
                    updated = self.ledger.transition(
                        candidate_id,
                        "replanning",
                        waiting_reason=None,
                        preempted_by_plan_id=None,
                        last_error=reason,
                        resume_decision="replan",
                        resume_reason=reason,
                    )
                    blocked.append(updated)
                    replans.append({
                        "actor_entity_id": actor,
                        "plan_id": candidate_id,
                        "decision": "replan",
                        "reason": reason,
                    })
                    continue

                updated = self.ledger.transition(
                    candidate_id,
                    "cancelled",
                    waiting_reason=None,
                    preempted_by_plan_id=None,
                    last_error=reason,
                    resume_decision="cancel",
                    resume_reason=reason,
                )
                cancellations.append({
                    "actor_entity_id": actor,
                    "plan_id": candidate_id,
                    "decision": "cancel",
                    "reason": reason,
                })

            if winner is None:
                continue

            winner_id = str(winner.get("plan_id") or "")
            runnable.append(winner)

            for loser in rows:
                loser_id = str(loser.get("plan_id") or "")
                if loser_id == winner_id:
                    continue
                latest = self.ledger.get(loser_id) or loser
                status = str(latest.get("status") or "")
                if status in {"planned", "running"}:
                    if status == "planned":
                        latest = self.ledger.transition(loser_id, "running")
                    self.ledger.transition(
                        loser_id,
                        "waiting",
                        waiting_reason="preempted",
                        preempted_by_plan_id=winner_id,
                        preemption_count=int(latest.get("preemption_count", 0)) + 1,
                        last_error=None,
                    )
                    preemptions.append({
                        "actor_entity_id": actor,
                        "plan_id": loser_id,
                        "preempted_by_plan_id": winner_id,
                    })

        runnable.extend(unowned)
        runnable = sorted(runnable, key=lambda row: str(row.get("plan_id") or ""))
        return {
            "runnable": [deepcopy(row) for row in runnable],
            "blocked": [deepcopy(row) for row in blocked],
            "preemptions": preemptions,
            "resumptions": resumptions,
            "replans": replans,
            "cancellations": cancellations,
        }