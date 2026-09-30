from __future__ import annotations

import json
import os
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any


class PlanLedgerError(ValueError):
    pass


class PlanLedger:
    """Append-only lifecycle ledger for persistent deterministic plans."""

    TERMINAL = frozenset({"completed", "failed", "cancelled"})
    ALLOWED = {
        "planned": frozenset({"running", "cancelled", "failed"}),
        "running": frozenset({"running", "waiting", "replanning", "completed", "failed", "cancelled"}),
        "waiting": frozenset({"running", "replanning", "failed", "cancelled"}),
        "replanning": frozenset({"running", "failed", "cancelled"}),
        "completed": frozenset(),
        "failed": frozenset(),
        "cancelled": frozenset(),
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Only nonterminal rows stay hot. Terminal rows use cold byte offsets.
        self._view_by_id: dict[str, dict[str, Any]] | None = None
        self._view_offsets: dict[str, int] = {}
        self._view_order: list[str] = []
        # Preserve original creation order without rescanning all historical
        # plans each tick. Terminal lifecycle transitions remove the ID.
        self._view_active_ids: dict[str, None] = {}
        self._view_idempotency: dict[str, str] = {}
        self._view_need_candidates: dict[str, int] = {}
        self._view_signature: tuple[int, int, int, int] | None = None

    @staticmethod
    def _eligible_need_candidate(row: dict[str, Any]) -> bool:
        intent = row.get("intent")
        return (
            row.get("status") == "completed"
            and isinstance(intent, dict)
            and bool(intent.get("need"))
            and intent.get("need_outcome_eligible") is not False
        )

    def _signature(self) -> tuple[int, int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def _ensure_view(self) -> None:
        if self._view_by_id is not None and self._view_signature == self._signature():
            return
        # Stream on restart. Never retain complete terminal plan objects.
        for _ in range(3):
            before = self._signature()
            offsets: dict[str, int] = {}
            hot: dict[str, dict[str, Any]] = {}
            keys: dict[str, str] = {}
            candidates: dict[str, int] = {}
            order: list[str] = []
            for offset, row in self._iter_rows_with_offsets():
                plan_id = str(row.get("plan_id") or "").strip()
                if not plan_id:
                    continue
                if plan_id not in offsets:
                    order.append(plan_id)
                offsets[plan_id] = offset
                keys[plan_id] = str(row.get("idempotency_key") or "")
                if row.get("status") not in self.TERMINAL:
                    hot[plan_id] = row
                else:
                    hot.pop(plan_id, None)
                if self._eligible_need_candidate(row):
                    candidates[plan_id] = offset
                else:
                    candidates.pop(plan_id, None)
            after = self._signature()
            if before == after:
                idempotency: dict[str, str] = {}
                for plan_id in order:
                    key = keys.get(plan_id, "")
                    if key:
                        idempotency.setdefault(key, plan_id)
                self._view_by_id = hot
                self._view_offsets = offsets
                self._view_order = order
                self._view_active_ids = {
                    plan_id: None for plan_id in order if plan_id in hot
                }
                self._view_idempotency = idempotency
                self._view_need_candidates = candidates
                self._view_signature = after
                return
        raise PlanLedgerError("plan ledger changed while rebuilding current state")

    def _iter_rows_with_offsets(self):
        # Stream durable rows; quarantine ONLY a torn final append.
        if not self.path.exists():
            return
        with self.path.open("rb") as fh:
            while True:
                offset = fh.tell()
                raw = fh.readline()
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8").strip()
                    if line:
                        row = json.loads(line)
                        if isinstance(row, dict):
                            yield offset, row
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    if fh.read(1):
                        raise PlanLedgerError(
                            f"corrupt plan ledger at byte {offset}"
                        ) from exc
                    self._quarantine_torn_tail(offset, raw)
                    break

    def _compaction_manifest(self) -> dict[str, Any] | None:
        manifest_path = self.path.with_name(self.path.name + ".compaction.json")
        if not manifest_path.exists():
            return None
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise PlanLedgerError("plan compaction manifest invalid") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != "live-infinita-hot-ledger-compaction/v1"
            or value.get("kind") != "plans"
            or value.get("source") != self.path.name
            or not isinstance(value.get("archive"), str)
            or type(value.get("latest_rows")) is not int
            or int(value["latest_rows"]) < 1
        ):
            raise PlanLedgerError("plan compaction manifest invalid")
        return value

    @staticmethod
    def _read_archive_history(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("rb") as fh:
            for line_number, raw in enumerate(fh, start=1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise PlanLedgerError(
                        f"plan archive corrupt at line {line_number}"
                    ) from exc
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def history(self) -> list[dict[str, Any]]:
        # Explicit full history; never used to rebuild the hot index.
        current_rows = [row for _, row in self._iter_rows_with_offsets()]
        manifest = self._compaction_manifest()
        if manifest is None:
            return current_rows
        archive = self.path.parent / str(manifest["archive"])
        if not archive.is_file() or archive.is_symlink():
            raise PlanLedgerError("plan compaction archive unavailable")
        boundary = int(manifest["latest_rows"])
        if len(current_rows) < boundary:
            raise PlanLedgerError("plan compact snapshot truncated")
        return self._read_archive_history(archive) + current_rows[boundary:]

    def _read_at(self, offset: int, expected_id: str) -> dict[str, Any]:
        try:
            with self.path.open("rb") as fh:
                fh.seek(offset)
                row = json.loads(fh.readline())
        except (OSError, ValueError, TypeError) as exc:
            raise PlanLedgerError("indexed plan record unavailable") from exc
        if not isinstance(row, dict) or str(row.get("plan_id") or "").strip() != expected_id:
            raise PlanLedgerError("indexed plan record identity mismatch")
        return row

    def _latest(self, plan_id: str) -> dict[str, Any] | None:
        assert self._view_by_id is not None
        hot = self._view_by_id.get(plan_id)
        if hot is not None:
            return deepcopy(hot)
        offset = self._view_offsets.get(plan_id)
        return self._read_at(offset, plan_id) if offset is not None else None

    def _quarantine_torn_tail(self, offset: int, raw: bytes) -> None:
        quarantine = self.path.with_name(self.path.name + ".torn-tail")
        try:
            with quarantine.open("ab") as fh:
                fh.write(raw)
                fh.flush()
                os.fsync(fh.fileno())
            with self.path.open("r+b") as fh:
                fh.truncate(offset)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise PlanLedgerError(
                f"unable to recover torn plan-ledger tail at byte {offset}"
            ) from exc

    def current(self) -> list[dict[str, Any]]:
        # Explicit complete snapshot. Per-tick consumers must use active/pending.
        self._ensure_view()
        return [row for plan_id in self._view_order
                if (row := self._latest(plan_id)) is not None]

    def get(self, plan_id: str) -> dict[str, Any] | None:
        self._ensure_view()
        return self._latest(str(plan_id or "").strip())

    def get_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        self._ensure_view()
        plan_id = self._view_idempotency.get(str(key or ""))
        return self._latest(plan_id) if plan_id else None

    def active(self) -> list[dict[str, Any]]:
        self._ensure_view()
        assert self._view_by_id is not None
        return [deepcopy(self._view_by_id[plan_id])
                for plan_id in self._view_active_ids]

    def has_active_plan_for_actor(self, actor_entity_id: str) -> bool:
        self._ensure_view()
        assert self._view_by_id is not None
        actor = str(actor_entity_id or "")
        return any(
            str(self._view_by_id[plan_id].get("actor_entity_id") or "") == actor
            for plan_id in self._view_active_ids
        )

    def need_outcome_candidates(self) -> list[dict[str, Any]]:
        self._ensure_view()
        return [
            self._read_at(self._view_need_candidates[plan_id], plan_id)
            for plan_id in self._view_order
            if plan_id in self._view_need_candidates
        ]

    def pending_need_outcome_candidates(self, processed_ids: set[str]) -> list[dict[str, Any]]:
        self._ensure_view()
        return [
            self._read_at(self._view_need_candidates[plan_id], plan_id)
            for plan_id in self._view_order
            if plan_id not in processed_ids and plan_id in self._view_need_candidates
        ]

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        before = self._signature()
        cached = self._view_by_id is not None and self._view_signature == before
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            written = os.write(fd, payload)
            if written != len(payload):
                raise PlanLedgerError(f"short plan-ledger append: {written}/{len(payload)} bytes")
            os.fsync(fd)
        except BaseException:
            self._view_by_id = None
            raise
        finally:
            os.close(fd)

        after = self._signature()
        expected_size = (before[2] if before else 0) + len(payload)
        if cached and after is not None and after[2] == expected_size and (
            before is None or after[:2] == before[:2]
        ):
            assert self._view_by_id is not None
            plan_id = str(row.get("plan_id") or "").strip()
            if plan_id:
                old_offset = self._view_offsets.get(plan_id)
                previous = self._latest(plan_id) if old_offset is not None else None
                previous_key = str(previous.get("idempotency_key") or "") if previous else ""
                key = str(row.get("idempotency_key") or "")
                if previous is not None and previous_key != key:
                    self._view_by_id = None
                else:
                    if old_offset is None:
                        self._view_order.append(plan_id)
                    offset = before[2] if before else 0
                    self._view_offsets[plan_id] = offset
                    if row.get("status") not in self.TERMINAL:
                        self._view_by_id[plan_id] = deepcopy(row)
                        if old_offset is not None and plan_id not in self._view_active_ids:
                            old_active = self._view_active_ids
                            self._view_active_ids = {
                                existing: None for existing in self._view_order
                                if existing == plan_id or existing in old_active
                            }
                        else:
                            self._view_active_ids.setdefault(plan_id, None)
                    else:
                        self._view_by_id.pop(plan_id, None)
                        self._view_active_ids.pop(plan_id, None)
                    if self._eligible_need_candidate(row):
                        self._view_need_candidates[plan_id] = offset
                    else:
                        self._view_need_candidates.pop(plan_id, None)
                    if key:
                        self._view_idempotency.setdefault(key, plan_id)
            self._view_signature = after
        else:
            self._view_by_id = None
        return row

    def create(
        self,
        *,
        proposal_id: str | None,
        proposer_id: str,
        principal: dict[str, Any],
        intent: dict[str, Any],
        plan: dict[str, Any],
        idempotency_key: str | None = None,
        priority: int = 0,
        actor_entity_id: str | None = None,
    ) -> dict[str, Any]:
        if idempotency_key:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
        now = time.time()
        actor = str(actor_entity_id or intent.get("actor_entity_id") or principal.get("subject_entity_id") or "").strip() or None
        row = {
            "plan_schema": "intent_plan_v4",
            "plan_id": f"plan_{int(now * 1000)}_{uuid.uuid4().hex[:10]}",
            "proposal_id": str(proposal_id or "").strip() or None,
            "proposer_id": str(proposer_id or "").strip(),
            "principal": deepcopy(principal),
            "intent": deepcopy(intent),
            "plan": deepcopy(plan),
            "plan_revision": 0,
            "plan_revision_history": [],
            "priority": int(priority),
            "actor_entity_id": actor,
            "status": "planned",
            "next_step_index": 0,
            "completed_steps": [],
            "waiting_reason": None,
            "preempted_by_plan_id": None,
            "preemption_count": 0,
            "replan_count": 0,
            "started_logical_tick": None,
            "completed_logical_tick": None,
            "idempotency_key": str(idempotency_key or "").strip() or None,
            "last_error": None,
            "created_at_unix": now,
            "updated_at_unix": now,
        }
        if not row["proposer_id"]:
            raise PlanLedgerError("proposer_id is required")
        return self._append(row)

    def transition(self, plan_id: str, status: str, **updates: Any) -> dict[str, Any]:
        current = self.get(plan_id)
        if current is None:
            raise KeyError("plan not found")
        old = str(current.get("status") or "")
        status = str(status or "").strip().lower()
        if status not in self.ALLOWED.get(old, frozenset()):
            raise PlanLedgerError(f"invalid transition: {old} -> {status}")
        row = deepcopy(current)
        row["status"] = status
        for key, value in updates.items():
            row[key] = deepcopy(value)
        row["updated_at_unix"] = time.time()
        return self._append(row)

    def replace_plan_revision(self, plan_id: str, *, plan: dict[str, Any], reason: str) -> dict[str, Any]:
        current = self.get(plan_id)
        if current is None:
            raise KeyError("plan not found")
        if str(current.get("status") or "") != "replanning":
            raise PlanLedgerError("plan replacement requires replanning status")

        revision = int(current.get("plan_revision", 0))
        history = list(current.get("plan_revision_history") or [])
        history.append({
            "plan_revision": revision,
            "plan": deepcopy(current.get("plan") or {}),
            "next_step_index": int(current.get("next_step_index", 0)),
            "reason": str(reason or "replanned"),
            "replaced_at_unix": time.time(),
        })
        return self.transition(
            plan_id,
            "running",
            plan=deepcopy(plan),
            plan_revision=revision + 1,
            plan_revision_history=history,
            replan_count=int(current.get("replan_count", 0)) + 1,
            next_step_index=0,
            waiting_reason=None,
            preempted_by_plan_id=None,
            last_error=None,
        )

    def mark_step_completed(
        self,
        plan_id: str,
        *,
        step_index: int,
        mutation_decision_id: str | None,
        world_event_id: str | None,
        state_hash: str | None,
        logical_tick: int | None = None,
    ) -> dict[str, Any]:
        current = self.get(plan_id)
        if current is None:
            raise KeyError("plan not found")
        expected = int(current.get("next_step_index", 0))
        if step_index != expected:
            raise PlanLedgerError(f"step out of order: {step_index} != {expected}")
        completed = list(current.get("completed_steps") or [])
        step_row = {
            "plan_revision": int(current.get("plan_revision", 0)),
            "step_index": step_index,
            "mutation_decision_id": mutation_decision_id,
            "world_event_id": world_event_id,
            "state_hash": state_hash,
        }
        if logical_tick is not None:
            step_row["logical_tick"] = int(logical_tick)
        completed.append(step_row)
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        next_index = step_index + 1
        status = "completed" if next_index >= len(steps) else "running"
        updates: dict[str, Any] = {
            "next_step_index": next_index,
            "completed_steps": completed,
            "waiting_reason": None,
            "preempted_by_plan_id": None,
            "last_error": None,
        }
        if current.get("started_logical_tick") is None and logical_tick is not None:
            updates["started_logical_tick"] = int(logical_tick)
        if status == "completed" and logical_tick is not None:
            updates["completed_logical_tick"] = int(logical_tick)
        return self.transition(plan_id, status, **updates)
