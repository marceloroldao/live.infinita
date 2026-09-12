from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from conditional_event_scheduler import ConditionalEventScheduler
from plan_scheduler import PlanScheduler


class ConditionalIntentBridge:
    """Create persistent plans from satisfied deterministic conditions.

    The condition is read-only and deterministic. When it fires, the bridge
    schedules a semantic intent through PlanScheduler instead of mutating the
    authoritative world directly. Idempotency is derived from condition id +
    fire ordinal unless an explicit key is supplied.
    """

    def __init__(
        self,
        conditions: ConditionalEventScheduler,
        plans: PlanScheduler,
    ) -> None:
        self.conditions = conditions
        self.plans = plans

    @staticmethod
    def _key(condition_id: str, fire_ordinal: int, explicit: str | None = None) -> str:
        if explicit:
            return str(explicit)
        payload = f"{condition_id}:{int(fire_ordinal)}".encode("utf-8")
        return "conditional-intent:" + hashlib.sha256(payload).hexdigest()[:24]

    def schedule_from_fired_condition(
        self,
        condition_row: dict[str, Any],
        *,
        intent: dict[str, Any],
        principal: dict[str, Any],
        proposer_id: str,
        proposal_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(condition_row, dict):
            raise ValueError("condition_row is required")
        condition_id = str(condition_row.get("conditional_event_id") or "").strip()
        if not condition_id:
            raise ValueError("conditional_event_id is required")
        fire_count = int(condition_row.get("fire_count", 0))
        if fire_count <= 0:
            raise ValueError("condition has not fired")
        return self.plans.schedule(
            intent=deepcopy(intent),
            principal=deepcopy(principal),
            proposer_id=str(proposer_id or "conditional-world").strip(),
            proposal_id=proposal_id,
            idempotency_key=self._key(condition_id, fire_count, idempotency_key),
        )

    def evaluate_and_schedule(
        self,
        tick: int,
        bindings: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Evaluate conditions, then schedule intents bound to newly fired rows.

        `bindings` is keyed by conditional_event_id and stores intent/principal/
        proposer metadata. Only rows whose fire_count increased during this tick
        create plans. The bridge itself performs no world mutation.
        """
        before = {
            str(row.get("conditional_event_id") or ""): int(row.get("fire_count", 0))
            for row in self.conditions.current()
        }
        rows = self.conditions.evaluate_tick(int(tick))
        results: list[dict[str, Any]] = []
        for row in rows:
            condition_id = str(row.get("conditional_event_id") or "").strip()
            binding = bindings.get(condition_id)
            if not binding:
                continue
            previous = int(before.get(condition_id, 0))
            current = int(row.get("fire_count", 0))
            if current <= previous:
                continue
            result = self.schedule_from_fired_condition(
                row,
                intent=dict(binding.get("intent") or {}),
                principal=dict(binding.get("principal") or {}),
                proposer_id=str(binding.get("proposer_id") or "conditional-world"),
                proposal_id=(str(binding.get("proposal_id") or "").strip() or None),
                idempotency_key=(str(binding.get("idempotency_key") or "").strip() or None),
            )
            results.append({
                "conditional_event_id": condition_id,
                "fire_count": current,
                "plan_id": result.get("plan_id"),
                "plan_status": result.get("status"),
            })
        return results
