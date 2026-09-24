from __future__ import annotations

import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from mutation_gate_service import GuardedMutationService
from packages.spatial import MutationPrincipal


class WorldEventScheduleError(ValueError):
    pass


class WorldEventScheduler:
    """Persistent logical-tick scheduler for non-character world events.

    Events are append-only lifecycle records. Due events are executed through
    GuardedMutationService, so scheduling never bypasses MutationGate.
    """

    TERMINAL = frozenset({"fired", "cancelled", "failed"})

    def __init__(self, path: Path, guarded_mutations: GuardedMutationService) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.guarded = guarded_mutations

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
            event_id = str(row.get("scheduled_event_id") or "").strip()
            if not event_id:
                continue
            if event_id not in latest:
                order.append(event_id)
            latest[event_id] = row
        return [latest[event_id] for event_id in order]

    def get(self, scheduled_event_id: str) -> dict[str, Any] | None:
        scheduled_event_id = str(scheduled_event_id or "").strip()
        return next((row for row in self.current() if row.get("scheduled_event_id") == scheduled_event_id), None)

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def schedule(
        self,
        *,
        due_tick: int,
        operations: list[dict[str, Any]],
        principal: MutationPrincipal | dict[str, Any],
        narration: str = "",
        recurrence_every_ticks: int | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if int(due_tick) < 0:
            raise WorldEventScheduleError("due_tick must be >= 0")
        if not operations:
            raise WorldEventScheduleError("operations are required")
        if recurrence_every_ticks is not None and int(recurrence_every_ticks) <= 0:
            raise WorldEventScheduleError("recurrence_every_ticks must be positive")
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

        key = str(idempotency_key or "").strip() or None
        if key:
            for row in self.current():
                if row.get("idempotency_key") == key:
                    return row

        now = time.time()
        row = {
            "schedule_schema": "world_event_schedule_v1",
            "scheduled_event_id": f"wev_{int(now * 1000)}_{uuid.uuid4().hex[:10]}",
            "status": "scheduled",
            "due_tick": int(due_tick),
            "recurrence_every_ticks": int(recurrence_every_ticks) if recurrence_every_ticks is not None else None,
            "operations": deepcopy(operations),
            "principal": principal_dict,
            "narration": str(narration or ""),
            "metadata": deepcopy(metadata or {}),
            "idempotency_key": key,
            "fire_count": 0,
            "last_world_event_id": None,
            "last_mutation_decision_id": None,
            "last_state_hash": None,
            "last_error": None,
            "created_at_unix": now,
            "updated_at_unix": now,
        }
        return self._append(row)

    def cancel(self, scheduled_event_id: str, *, reason: str = "cancelled") -> dict[str, Any]:
        current = self.get(scheduled_event_id)
        if current is None:
            raise KeyError("scheduled event not found")
        if current.get("status") in self.TERMINAL:
            return current
        row = deepcopy(current)
        row["status"] = "cancelled"
        row["last_error"] = str(reason or "cancelled")[:1000]
        row["updated_at_unix"] = time.time()
        return self._append(row)

    def due(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        rows = [
            row for row in self.current()
            if row.get("status") == "scheduled" and int(row.get("due_tick", -1)) <= tick
        ]
        return sorted(rows, key=lambda row: (int(row.get("due_tick", 0)), str(row.get("scheduled_event_id") or "")))

    def fire_due(self, tick: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for row in self.due(tick):
            event_id = str(row["scheduled_event_id"])
            result = self.guarded.commit(
                list(row.get("operations") or []),
                principal=dict(row.get("principal") or {}),
                context={
                    "scheduled_event_id": event_id,
                    "due_tick": int(row.get("due_tick", 0)),
                    "fired_at_tick": int(tick),
                    "schedule_metadata": deepcopy(row.get("metadata") or {}),
                },
                narration=str(row.get("narration") or f"scheduled world event {event_id}"),
            )
            updated = deepcopy(row)
            updated["updated_at_unix"] = time.time()
            audit = result.get("audit") or {}
            updated["last_mutation_decision_id"] = str(audit.get("mutation_decision_id") or "").strip() or None
            if not result.get("ok"):
                updated["status"] = "failed"
                updated["last_error"] = str((result.get("decision") or {}).get("reason") or "mutation rejected")[:1000]
                self._append(updated)
                results.append(updated)
                continue

            world = result.get("world") or {}
            event = result.get("event") or {}
            updated["fire_count"] = int(updated.get("fire_count", 0)) + 1
            updated["last_world_event_id"] = str(event.get("event_id") or "").strip() or None
            updated["last_state_hash"] = str(world.get("state_hash") or "").strip() or None
            updated["last_error"] = None
            recurrence = updated.get("recurrence_every_ticks")
            if recurrence is None:
                updated["status"] = "fired"
            else:
                updated["status"] = "scheduled"
                updated["due_tick"] = int(updated.get("due_tick", tick)) + int(recurrence)
            self._append(updated)
            results.append(updated)
        return results
