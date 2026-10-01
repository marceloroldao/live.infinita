from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from mutation_gate_service import GuardedMutationService
from packages.spatial import MutationPrincipal


class ConditionalEventError(ValueError):
    pass


class ConditionalEventScheduler:
    """Evaluate deterministic state predicates once per logical tick.

    A trigger can produce either a guarded canonical mutation or a semantic
    intent plan. Plan creation itself never mutates world state; plan steps later
    pass through the normal PlanScheduler + MutationGate path.
    """

    TERMINAL = frozenset({"completed", "cancelled", "failed"})
    SUPPORTED = frozenset({
        "entity_in_region",
        "world_equals",
        "entity_property_equals",
        "all",
        "any",
        "not",
        "nobody_near_entity",
    })

    def __init__(
        self,
        path: Path,
        guarded_mutations: GuardedMutationService,
        plan_dispatcher: Any | None = None,
        stage_observer: Callable[[str, int], None] | None = None,
        monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.guarded = guarded_mutations
        self.plan_dispatcher = plan_dispatcher
        self.stage_observer = stage_observer
        self.monotonic_ns = monotonic_ns
        self._view_by_id: dict[str, dict[str, Any]] | None = None
        self._view_order: list[str] = []
        self._view_signature: tuple[int, int, int, int] | None = None

    def _stage(self, name: str, fn: Callable[[], Any]) -> Any:
        if self.stage_observer is None:
            return fn()
        started = self.monotonic_ns()
        try:
            return fn()
        finally:
            try:
                self.stage_observer(name, max(0, self.monotonic_ns() - started))
            except Exception:
                pass

    def _signature(self) -> tuple[int, int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def _ensure_view(self) -> None:
        if self._view_by_id is not None and self._view_signature == self._signature():
            return
        # Only active/latest records are materialized; the full JSONL stays
        # authoritative for history and recovery. External changes invalidate.
        for _ in range(3):
            before = self._signature()
            latest: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for row in self._iter_history():
                event_id = str(row.get("conditional_event_id") or "").strip()
                if not event_id:
                    continue
                if event_id not in latest:
                    order.append(event_id)
                latest[event_id] = row
            after = self._signature()
            if before == after:
                self._view_by_id = latest
                self._view_order = order
                self._view_signature = after
                return
        raise ConditionalEventError("conditional ledger changed while rebuilding current state")

    def _iter_history(self):
        """Stream durable JSONL records and repair only a malformed final record."""
        if not self.path.exists():
            return
        pending: tuple[int, bytes] | None = None
        with self.path.open("rb") as fh:
            while True:
                offset = fh.tell()
                raw = fh.readline()
                if not raw:
                    break
                if not raw.strip():
                    continue
                if pending is not None:
                    _, previous = pending
                    try:
                        value = json.loads(previous.strip().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        # Once a later durable record exists, corruption is not a
                        # recoverable crash tail and must remain a hard failure.
                        raise
                    if isinstance(value, dict):
                        yield value
                pending = (offset, raw)

        if pending is None:
            return
        offset, raw = pending
        try:
            value = json.loads(raw.strip().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            quarantine = self.path.with_suffix(self.path.suffix + ".truncated")
            quarantine.write_bytes(raw)
            with self.path.open("r+b") as fh:
                fh.truncate(offset)
                fh.flush()
                os.fsync(fh.fileno())
            return
        if isinstance(value, dict):
            yield value

    def repair_legacy_single_invalid_record(self) -> dict[str, Any]:
        """One-time migration for the historical tail-then-append corruption bug.

        Older builds could ignore a truncated tail and later append a valid row,
        converting the fragment into mid-log corruption. Preserve a full backup
        and quarantine the exact invalid bytes before removing one such record.
        Multiple invalid records remain a hard failure.
        """
        marker = self.path.with_suffix(self.path.suffix + ".legacy-repair-v1.json")
        if marker.exists() or not self.path.exists():
            return {"repaired": False, "reason": "already_checked" if marker.exists() else "missing"}

        invalid: list[tuple[int, bytes]] = []
        with self.path.open("rb") as fh:
            for line_number, raw in enumerate(fh, start=1):
                if not raw.strip():
                    continue
                try:
                    json.loads(raw.strip().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    invalid.append((line_number, raw))
                    if len(invalid) > 1:
                        raise ConditionalEventError("legacy JSONL repair found multiple invalid records")

        if not invalid:
            marker.write_text(json.dumps({"repaired": False, "reason": "clean"}, sort_keys=True) + "\\n", encoding="utf-8")
            return {"repaired": False, "reason": "clean"}

        bad_line, bad_raw = invalid[0]
        backup = self.path.with_suffix(self.path.suffix + ".legacy-repair-v1.bak")
        quarantine = self.path.with_suffix(self.path.suffix + ".legacy-repair-v1.corrupt")
        temporary = self.path.with_suffix(self.path.suffix + ".legacy-repair-v1.tmp")
        shutil.copy2(self.path, backup)
        quarantine.write_bytes(bad_raw)
        with self.path.open("rb") as source, temporary.open("wb") as target:
            for line_number, raw in enumerate(source, start=1):
                if line_number != bad_line:
                    target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, self.path)
        marker.write_text(json.dumps({
            "repaired": True,
            "removed_line": bad_line,
            "backup": backup.name,
            "quarantine": quarantine.name,
        }, sort_keys=True) + "\\n", encoding="utf-8")
        return {"repaired": True, "removed_line": bad_line}

    def _compaction_manifest(self) -> dict[str, Any] | None:
        manifest_path = self.path.with_name(self.path.name + ".compaction.json")
        if not manifest_path.exists():
            return None
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ConditionalEventError("conditional compaction manifest invalid") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != "live-infinita-hot-ledger-compaction/v1"
            or value.get("kind") != "conditional"
            or value.get("source") != self.path.name
            or not isinstance(value.get("archive"), str)
            or type(value.get("latest_rows")) is not int
            or int(value["latest_rows"]) < 1
        ):
            raise ConditionalEventError("conditional compaction manifest invalid")
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
                    raise ConditionalEventError(
                        f"conditional archive corrupt at line {line_number}"
                    ) from exc
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def history(self) -> list[dict[str, Any]]:
        manifest = self._compaction_manifest()
        current_rows = list(self._iter_history())
        if manifest is None:
            return current_rows
        archive = self.path.parent / str(manifest["archive"])
        if not archive.is_file() or archive.is_symlink():
            raise ConditionalEventError("conditional compaction archive unavailable")
        # The first latest_rows entries in the hot file are the synthetic
        # current-state snapshot. They duplicate rows already present in archive.
        boundary = int(manifest["latest_rows"])
        if len(current_rows) < boundary:
            raise ConditionalEventError("conditional compact snapshot truncated")
        return self._read_archive_history(archive) + current_rows[boundary:]

    def current(self) -> list[dict[str, Any]]:
        self._ensure_view()
        assert self._view_by_id is not None
        return [deepcopy(self._view_by_id[event_id]) for event_id in self._view_order]

    def get(self, conditional_event_id: str) -> dict[str, Any] | None:
        self._ensure_view()
        assert self._view_by_id is not None
        row = self._view_by_id.get(str(conditional_event_id or "").strip())
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
            before is None or after[:2] == before[:2]
        ):
            assert self._view_by_id is not None
            event_id = str(row.get("conditional_event_id") or "").strip()
            if event_id:
                if event_id not in self._view_by_id:
                    self._view_order.append(event_id)
                self._view_by_id[event_id] = deepcopy(row)
            self._view_signature = after
        else:
            self._view_by_id = None
        return row

    def _cache_only(self, row: dict[str, Any]) -> None:
        """Advance ephemeral evaluation metadata without growing durable history."""
        if self._view_by_id is None or self._view_signature != self._signature():
            return
        event_id = str(row.get("conditional_event_id") or "").strip()
        if event_id and event_id in self._view_by_id:
            self._view_by_id[event_id] = deepcopy(row)

    @staticmethod
    def _principal_dict(principal: MutationPrincipal | dict[str, Any]) -> dict[str, Any]:
        if isinstance(principal, MutationPrincipal):
            return {
                "source": principal.source,
                "actor_id": principal.actor_id,
                "authority": principal.authority,
                "subject_entity_id": principal.subject_entity_id,
            }
        result = dict(principal)
        MutationPrincipal.from_dict(result)
        return result

    def _validate_condition(self, condition: dict[str, Any]) -> None:
        if not isinstance(condition, dict):
            raise ConditionalEventError("condition must be an object")
        kind = str(condition.get("kind") or "").strip().lower()
        if kind not in self.SUPPORTED:
            raise ConditionalEventError(f"unsupported condition kind: {kind}")
        sustain = int(condition.get("sustain_ticks", 0) or 0)
        if sustain < 0:
            raise ConditionalEventError("sustain_ticks must be >= 0")
        if kind in {"all", "any"}:
            conditions = condition.get("conditions")
            if not isinstance(conditions, list) or not conditions:
                raise ConditionalEventError(f"{kind} requires non-empty conditions")
            for child in conditions:
                self._validate_condition(child)
        elif kind == "not":
            child = condition.get("condition")
            if not isinstance(child, dict):
                raise ConditionalEventError("not requires condition")
            self._validate_condition(child)
        elif kind == "nobody_near_entity":
            if not str(condition.get("anchor_entity_id") or "").strip():
                raise ConditionalEventError("nobody_near_entity requires anchor_entity_id")
            radius = float(condition.get("radius", 0) or 0)
            if radius <= 0:
                raise ConditionalEventError("nobody_near_entity radius must be positive")

    def register(
        self,
        *,
        condition: dict[str, Any],
        principal: MutationPrincipal | dict[str, Any],
        operations: list[dict[str, Any]] | None = None,
        intent: dict[str, Any] | None = None,
        trigger_mode: str = "edge",
        cooldown_ticks: int = 0,
        one_shot: bool = False,
        narration: str = "",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._validate_condition(condition)
        trigger_mode = str(trigger_mode or "edge").strip().lower()
        if trigger_mode not in {"edge", "level"}:
            raise ConditionalEventError("trigger_mode must be edge or level")
        if int(cooldown_ticks) < 0:
            raise ConditionalEventError("cooldown_ticks must be >= 0")
        has_operations = bool(operations)
        has_intent = isinstance(intent, dict) and bool(intent)
        if has_operations == has_intent:
            raise ConditionalEventError("exactly one effect is required: operations or intent")
        if has_intent and self.plan_dispatcher is None:
            raise ConditionalEventError("plan_intent effect requires plan_dispatcher")

        key = str(idempotency_key or "").strip() or None
        if key:
            for row in self.current():
                if row.get("idempotency_key") == key:
                    return row

        now = time.time()
        row = {
            "conditional_schema": "conditional_world_event_v3",
            "conditional_event_id": f"cev_{int(now * 1000)}_{uuid.uuid4().hex[:10]}",
            "status": "active",
            "condition": deepcopy(condition),
            "effect_kind": "plan_intent" if has_intent else "mutation",
            "operations": deepcopy(operations or []),
            "intent": deepcopy(intent) if has_intent else None,
            "principal": self._principal_dict(principal),
            "trigger_mode": trigger_mode,
            "cooldown_ticks": int(cooldown_ticks),
            "one_shot": bool(one_shot),
            "narration": str(narration or ""),
            "metadata": deepcopy(metadata or {}),
            "idempotency_key": key,
            "last_condition_value": False,
            "last_raw_condition_value": False,
            "true_since_tick": None,
            "last_evaluated_tick": None,
            "last_fired_tick": None,
            "fire_count": 0,
            "last_world_event_id": None,
            "last_mutation_decision_id": None,
            "last_state_hash": None,
            "last_proposal_id": None,
            "last_plan_id": None,
            "last_error": None,
            "created_at_unix": now,
            "updated_at_unix": now,
        }
        return self._append(row)

    def cancel(self, conditional_event_id: str, *, reason: str = "cancelled") -> dict[str, Any]:
        row = self.get(conditional_event_id)
        if row is None:
            raise KeyError("conditional event not found")
        if row.get("status") in self.TERMINAL:
            return row
        updated = deepcopy(row)
        updated["status"] = "cancelled"
        updated["last_error"] = str(reason)[:1000]
        updated["updated_at_unix"] = time.time()
        return self._append(updated)

    @staticmethod
    def _nested(value: Any, path: list[Any]) -> Any:
        cursor = value
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return None
            cursor = cursor[key]
        return cursor

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        engine = self.guarded.engine
        cold_store = getattr(engine, "cold_store", None)
        if cold_store is not None:
            return cold_store.get_entity(entity_id)
        world = engine.load_world()
        entities = world.get("entities") if isinstance(world.get("entities"), list) else []
        return next((row for row in entities if isinstance(row, dict) and row.get("id") == entity_id), None)

    def _region_entities(self, region_id: str) -> list[dict[str, Any]]:
        engine = self.guarded.engine
        cold_store = getattr(engine, "cold_store", None)
        if cold_store is not None and hasattr(cold_store, "load_region"):
            return cold_store.load_region(region_id)
        world = engine.load_world()
        entities = world.get("entities") if isinstance(world.get("entities"), list) else []
        return [row for row in entities if isinstance(row, dict) and str(row.get("region_id") or "") == region_id]

    @staticmethod
    def _position(entity: dict[str, Any]) -> tuple[float, float] | None:
        position = entity.get("position")
        if not isinstance(position, dict):
            return None
        try:
            return float(position["x"]), float(position["y"])
        except (KeyError, TypeError, ValueError):
            return None

    def evaluate_condition(self, condition: dict[str, Any]) -> bool:
        kind = str(condition.get("kind") or "").strip().lower()
        if kind == "entity_in_region":
            entity_id = str(condition.get("entity_id") or "").strip()
            region_id = str(condition.get("region_id") or "").strip()
            entity = self._entity(entity_id)
            return bool(entity and str(entity.get("region_id") or "") == region_id)

        if kind == "world_equals":
            path = condition.get("path")
            if not isinstance(path, list) or not path:
                raise ConditionalEventError("world_equals requires path")
            world = self._stage(
                "conditional.condition.load_world",
                self.guarded.engine.load_world,
            )
            return self._nested(world, path) == condition.get("value")

        if kind == "entity_property_equals":
            entity_id = str(condition.get("entity_id") or "").strip()
            path = condition.get("path")
            if not isinstance(path, list) or not path:
                raise ConditionalEventError("entity_property_equals requires path")
            entity = self._entity(entity_id)
            return bool(entity is not None and self._nested(entity, path) == condition.get("value"))

        if kind in {"all", "any"}:
            children = [self.evaluate_condition(dict(child)) for child in condition.get("conditions", [])]
            return all(children) if kind == "all" else any(children)

        if kind == "not":
            return not self.evaluate_condition(dict(condition.get("condition") or {}))

        if kind == "nobody_near_entity":
            anchor_id = str(condition.get("anchor_entity_id") or "").strip()
            anchor = self._entity(anchor_id)
            if anchor is None:
                return False
            anchor_pos = self._position(anchor)
            region_id = str(anchor.get("region_id") or "").strip()
            if anchor_pos is None or not region_id:
                return False
            radius = float(condition.get("radius", 0))
            radius_sq = radius * radius
            exclude_ids = {str(v) for v in condition.get("exclude_entity_ids", []) if str(v)}
            exclude_ids.add(anchor_id)
            allowed_types = {str(v) for v in condition.get("entity_types", []) if str(v)}
            ax, ay = anchor_pos
            for entity in self._region_entities(region_id):
                entity_id = str(entity.get("id") or "")
                if entity_id in exclude_ids:
                    continue
                if allowed_types and str(entity.get("type") or "") not in allowed_types:
                    continue
                position = self._position(entity)
                if position is None:
                    continue
                dx = position[0] - ax
                dy = position[1] - ay
                if dx * dx + dy * dy <= radius_sq:
                    return False
            return True

        raise ConditionalEventError(f"unsupported condition kind: {kind}")

    @staticmethod
    def _sustained_value(row: dict[str, Any], raw_value: bool, tick: int) -> tuple[bool, int | None]:
        condition = row.get("condition") if isinstance(row.get("condition"), dict) else {}
        sustain_ticks = int(condition.get("sustain_ticks", 0) or 0)
        if not raw_value:
            return False, None
        previous_raw = bool(row.get("last_raw_condition_value", False))
        true_since = row.get("true_since_tick")
        if not previous_raw or true_since is None:
            true_since = tick
        if sustain_ticks <= 1:
            return True, int(true_since)
        return tick - int(true_since) + 1 >= sustain_ticks, int(true_since)

    def evaluate_tick(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        results: list[dict[str, Any]] = []
        active = self._stage(
            "conditional.evaluate.current",
            lambda: sorted(
                [row for row in self.current() if row.get("status") == "active"],
                key=lambda row: str(row.get("conditional_event_id") or ""),
            ),
        )
        for row in active:
            updated = deepcopy(row)
            try:
                raw_value = self._stage(
                    "conditional.evaluate.condition",
                    lambda: self.evaluate_condition(dict(row.get("condition") or {})),
                )
                value, true_since = self._sustained_value(row, raw_value, tick)
            except Exception as exc:
                updated["status"] = "failed"
                updated["last_error"] = str(exc)[:1000]
                updated["last_evaluated_tick"] = tick
                updated["updated_at_unix"] = time.time()
                self._append(updated)
                results.append(updated)
                continue

            previous = bool(row.get("last_condition_value", False))
            last_fired = row.get("last_fired_tick")
            cooldown = int(row.get("cooldown_ticks", 0))
            cooldown_ok = last_fired is None or tick - int(last_fired) >= cooldown
            trigger_mode = str(row.get("trigger_mode") or "edge")
            should_fire = value and cooldown_ok and (trigger_mode == "level" or not previous)

            updated["last_raw_condition_value"] = raw_value
            updated["true_since_tick"] = true_since
            updated["last_condition_value"] = value
            updated["last_evaluated_tick"] = tick

            if should_fire:
                conditional_id = str(row.get("conditional_event_id") or "")
                if row.get("effect_kind") == "plan_intent":
                    try:
                        dispatch = self._stage(
                            "conditional.evaluate.plan_dispatch",
                            lambda: self.plan_dispatcher.dispatch(
                            conditional_event_id=conditional_id,
                            tick=tick,
                            fire_index=int(row.get("fire_count", 0)) + 1,
                            intent=deepcopy(row.get("intent") or {}),
                            principal=deepcopy(row.get("principal") or {}),
                            metadata={
                                "condition": deepcopy(row.get("condition") or {}),
                                "true_since_tick": true_since,
                                **deepcopy(row.get("metadata") or {}),
                            },
                            ),
                        )
                        proposal = dispatch.get("proposal") or {}
                        plan = dispatch.get("plan") or {}
                        updated["fire_count"] = int(updated.get("fire_count", 0)) + 1
                        updated["last_fired_tick"] = tick
                        updated["last_proposal_id"] = str(proposal.get("proposal_id") or "").strip() or None
                        updated["last_plan_id"] = str(plan.get("plan_id") or "").strip() or None
                        updated["last_error"] = None
                        if bool(updated.get("one_shot")):
                            updated["status"] = "completed"
                    except Exception as exc:
                        updated["status"] = "failed"
                        updated["last_error"] = str(exc)[:1000]
                else:
                    result = self._stage(
                        "conditional.evaluate.guarded_commit",
                        lambda: self.guarded.commit(
                        list(row.get("operations") or []),
                        principal=dict(row.get("principal") or {}),
                        context={
                            "conditional_event_id": conditional_id,
                            "condition": deepcopy(row.get("condition") or {}),
                            "true_since_tick": true_since,
                            "fired_at_tick": tick,
                            "conditional_metadata": deepcopy(row.get("metadata") or {}),
                        },
                        narration=str(row.get("narration") or f"conditional world event {conditional_id}"),
                        ),
                    )
                    audit = result.get("audit") or {}
                    updated["last_mutation_decision_id"] = str(audit.get("mutation_decision_id") or "").strip() or None
                    if not result.get("ok"):
                        updated["status"] = "failed"
                        updated["last_error"] = str((result.get("decision") or {}).get("reason") or "mutation rejected")[:1000]
                    else:
                        world = result.get("world") or {}
                        event = result.get("event") or {}
                        updated["fire_count"] = int(updated.get("fire_count", 0)) + 1
                        updated["last_fired_tick"] = tick
                        updated["last_world_event_id"] = str(event.get("event_id") or "").strip() or None
                        updated["last_state_hash"] = str(world.get("state_hash") or "").strip() or None
                        updated["last_error"] = None
                        if bool(updated.get("one_shot")):
                            updated["status"] = "completed"

            durable_fields = (
                "status",
                "last_error",
                "last_raw_condition_value",
                "true_since_tick",
                "last_condition_value",
                "last_fired_tick",
                "fire_count",
                "last_world_event_id",
                "last_mutation_decision_id",
                "last_state_hash",
                "last_proposal_id",
                "last_plan_id",
            )
            durable_changed = any(updated.get(key) != row.get(key) for key in durable_fields)
            if durable_changed:
                updated["updated_at_unix"] = time.time()
                self._stage(
                    "conditional.evaluate.append",
                    lambda: self._append(updated),
                )
            else:
                # The logical tick is useful to in-process diagnostics but is not
                # a state transition. Persisting it every 500 ms previously grew
                # this two-condition ledger by hundreds of MB per day.
                self._stage(
                    "conditional.evaluate.cache_only",
                    lambda: self._cache_only(updated),
                )
            results.append(updated)
        return results
