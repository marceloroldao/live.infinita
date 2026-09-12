from __future__ import annotations

import json
import math
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

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
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.guarded = guarded_mutations
        self.plan_dispatcher = plan_dispatcher

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
            event_id = str(row.get("conditional_event_id") or "").strip()
            if not event_id:
                continue
            if event_id not in latest:
                order.append(event_id)
            latest[event_id] = row
        return [latest[event_id] for event_id in order]

    def get(self, conditional_event_id: str) -> dict[str, Any] | None:
        return next((row for row in self.current() if row.get("conditional_event_id") == conditional_event_id), None)

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

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
            world = self.guarded.engine.load_world()
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
        active = sorted(
            [row for row in self.current() if row.get("status") == "active"],
            key=lambda row: str(row.get("conditional_event_id") or ""),
        )
        for row in active:
            updated = deepcopy(row)
            try:
                raw_value = self.evaluate_condition(dict(row.get("condition") or {}))
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
            updated["updated_at_unix"] = time.time()

            if should_fire:
                conditional_id = str(row.get("conditional_event_id") or "")
                if row.get("effect_kind") == "plan_intent":
                    try:
                        dispatch = self.plan_dispatcher.dispatch(
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
                    result = self.guarded.commit(
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

            self._append(updated)
            results.append(updated)
        return results
