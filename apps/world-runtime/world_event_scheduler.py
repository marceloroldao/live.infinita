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
        for _ in range(3):
            before = self._signature()
            latest: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for row in self.history():
                event_id = str(row.get("scheduled_event_id") or "").strip()
                if not event_id:
                    continue
                if event_id not in latest:
                    order.append(event_id)
                latest[event_id] = row
            after = self._signature()
            if before == after:
                keys: dict[str, str] = {}
                for event_id in order:
                    key = str(latest[event_id].get("idempotency_key") or "")
                    if key:
                        keys.setdefault(key, event_id)
                self._view_by_id = latest
                self._view_order = order
                self._view_idempotency = keys
                self._view_signature = after
                return
        raise WorldEventScheduleError("world event schedule changed while replaying")

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
        self._ensure_view()
        assert self._view_by_id is not None
        return [deepcopy(self._view_by_id[event_id]) for event_id in self._view_order]

    def get(self, scheduled_event_id: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        row = self._view_by_id.get(str(scheduled_event_id or "").strip())
        return deepcopy(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        event_id = self._view_idempotency.get(str(key or ""))
        row = self._view_by_id.get(event_id) if event_id else None
        return deepcopy(row) if row is not None else None

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
            before is None or before[:2] == after[:2]
        ):
            assert self._view_by_id is not None
            event_id = str(row.get("scheduled_event_id") or "").strip()
            if event_id:
                previous = self._view_by_id.get(event_id)
                old_key = str(previous.get("idempotency_key") or "") if previous else ""
                key = str(row.get("idempotency_key") or "")
                if previous is not None and old_key != key:
                    self._view_by_id = None
                else:
                    if previous is None:
                        self._view_order.append(event_id)
                    self._view_by_id[event_id] = deepcopy(row)
                    if key:
                        self._view_idempotency.setdefault(key, event_id)
            self._view_signature = after
        else:
            self._view_by_id = None
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
            existing = self.get_by_idempotency_key(key)
            if existing is not None:
                return existing

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
        self._ensure_view()
        assert self._view_by_id is not None
        selected = [
            row for row in self._view_by_id.values()
            if row.get("status") == "scheduled" and int(row.get("due_tick", -1)) <= tick
        ]
        return [
            deepcopy(row)
            for row in sorted(
                selected,
                key=lambda row: (int(row.get("due_tick", 0)), str(row.get("scheduled_event_id") or "")),
            )
        ]

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
