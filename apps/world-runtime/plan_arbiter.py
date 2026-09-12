from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from plan_ledger import PlanLedger


class PlanArbiter:
    """Deterministic per-actor priority arbiter for persistent plans.

    At most one non-terminal plan per actor is runnable. Higher priority wins;
    ties are resolved by creation time then plan_id. Preempted plans are kept in
    `waiting` and can resume when the dominating plan becomes terminal.
    """

    def __init__(self, ledger: PlanLedger) -> None:
        self.ledger = ledger

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
        # Higher priority first; for equal priority keep oldest plan first.
        return (-cls._priority(record), float(record.get("created_at_unix", 0.0)), str(record.get("plan_id") or ""))

    def reconcile(self) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        unowned: list[dict[str, Any]] = []
        for record in self.ledger.active():
            actor = self.actor_id(record)
            if actor:
                groups[actor].append(record)
            else:
                unowned.append(record)

        runnable: list[dict[str, Any]] = []
        preemptions: list[dict[str, Any]] = []
        resumptions: list[dict[str, Any]] = []

        for actor in sorted(groups):
            rows = sorted(groups[actor], key=self._rank)
            winner = rows[0]
            winner_id = str(winner.get("plan_id") or "")
            winner_status = str(winner.get("status") or "")
            if winner_status == "waiting" and str(winner.get("waiting_reason") or "") == "preempted":
                winner = self.ledger.transition(
                    winner_id,
                    "running",
                    waiting_reason=None,
                    preempted_by_plan_id=None,
                    last_error=None,
                )
                resumptions.append({"actor_entity_id": actor, "plan_id": winner_id})
            runnable.append(winner)

            for loser in rows[1:]:
                loser_id = str(loser.get("plan_id") or "")
                status = str(loser.get("status") or "")
                if status in {"planned", "running"}:
                    # planned cannot transition directly to waiting in v1 ledger;
                    # first establish it as running, then persist the preemption.
                    if status == "planned":
                        loser = self.ledger.transition(loser_id, "running")
                    loser = self.ledger.transition(
                        loser_id,
                        "waiting",
                        waiting_reason="preempted",
                        preempted_by_plan_id=winner_id,
                        last_error=None,
                    )
                    preemptions.append({
                        "actor_entity_id": actor,
                        "plan_id": loser_id,
                        "preempted_by_plan_id": winner_id,
                    })

        # Plans with no actor do not conflict and remain runnable.
        runnable.extend(unowned)
        runnable = sorted(runnable, key=lambda row: str(row.get("plan_id") or ""))
        return {
            "runnable": [deepcopy(row) for row in runnable],
            "preemptions": preemptions,
            "resumptions": resumptions,
        }
