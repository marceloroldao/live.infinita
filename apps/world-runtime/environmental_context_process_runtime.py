from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class EnvironmentalContextProcessPhase:
    phase_id: str
    action_id: str
    next_phase_id: str
    route_overrides: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class EnvironmentalContextProcessRule:
    rule_id: str
    entity_id: str
    min_ticks: int
    state_component: str
    phase_field: str
    phases: tuple[EnvironmentalContextProcessPhase, ...]


@dataclass(frozen=True, slots=True)
class EnvironmentalContextProcessTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    transitions: tuple[dict[str, Any], ...]


def _rules(world: dict[str, Any]) -> tuple[EnvironmentalContextProcessRule, ...]:
    parsed: list[EnvironmentalContextProcessRule] = []
    for raw in (world.get("rules") or {}).get("environmental_context_processes") or ():
        rule_id = str((raw or {}).get("rule_id") or "")
        entity_id = str((raw or {}).get("entity") or "")
        state_component = str((raw or {}).get("state_component") or "")
        phase_field = str((raw or {}).get("phase_field") or "phase_id")
        min_ticks = int((raw or {}).get("min_ticks", 1))
        if not rule_id or not entity_id or not state_component:
            raise ValueError("context process rule is incomplete")
        if min_ticks < 1:
            raise ValueError("context process min_ticks must be >= 1")

        phases: list[EnvironmentalContextProcessPhase] = []
        seen: set[str] = set()
        for phase in (raw or {}).get("phases") or ():
            phase_id = str((phase or {}).get("phase_id") or "")
            action_id = str((phase or {}).get("action_id") or "")
            next_phase_id = str((phase or {}).get("next_phase_id") or "")
            if (
                not phase_id
                or phase_id in seen
                or not action_id
                or not next_phase_id
            ):
                raise ValueError(
                    "context process phases require unique phase/action/next IDs"
                )
            seen.add(phase_id)

            overrides: list[dict[str, Any]] = []
            for override in (phase or {}).get("route_overrides") or ():
                region_id = str((override or {}).get("region_id") or "")
                route_id = str((override or {}).get("route_id") or "")
                available = (override or {}).get("available")
                if not region_id or not route_id or not isinstance(available, bool):
                    raise ValueError(
                        "context process route override requires region_id, "
                        "route_id and bool available"
                    )
                overrides.append(
                    {
                        "region_id": region_id,
                        "route_id": route_id,
                        "available": available,
                    }
                )
            if not overrides:
                raise ValueError(
                    "context process phase requires at least one route override"
                )
            phases.append(
                EnvironmentalContextProcessPhase(
                    phase_id=phase_id,
                    action_id=action_id,
                    next_phase_id=next_phase_id,
                    route_overrides=tuple(overrides),
                )
            )

        phase_ids = {item.phase_id for item in phases}
        if not phases or any(item.next_phase_id not in phase_ids for item in phases):
            raise ValueError("context process phase graph must be closed")
        phases.sort(key=lambda item: item.phase_id)
        parsed.append(
            EnvironmentalContextProcessRule(
                rule_id=rule_id,
                entity_id=entity_id,
                min_ticks=min_ticks,
                state_component=state_component,
                phase_field=phase_field,
                phases=tuple(phases),
            )
        )

    parsed.sort(key=lambda item: item.rule_id)
    return tuple(parsed)


def _apply_route_overrides(
    world: dict[str, Any],
    overrides: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    operations: list[dict[str, Any]] = []
    for override in overrides:
        region_id = override["region_id"]
        route_id = override["route_id"]
        region = (world.get("regions") or {}).get(region_id)
        if not isinstance(region, dict):
            raise ValueError("context process override references missing region")
        routes = region.get("environmental_routes") or ()
        route_index = None
        for index, route in enumerate(routes):
            if str((route or {}).get("route_id") or "") == route_id:
                route["available"] = override["available"]
                route_index = index
                break
        if route_index is None:
            raise ValueError("context process override references missing route")
        operations.append(
            {
                "op": "set",
                "path": (
                    f"/regions/{region_id}/environmental_routes/"
                    f"{route_index}/available"
                ),
                "value": override["available"],
            }
        )
    return tuple(operations)


def advance_environmental_context_processes(
    world: dict[str, Any],
    *,
    ticks: int = 1,
) -> tuple[EnvironmentalContextProcessTick, ...]:
    """Advance autonomous world context processes through their own phase graphs.

    A context process is not an observer and does not consult Memoria.ia. Its current
    phase determines a physical route constraint, then the process advances to its
    next phase and records the transition in authoritative Event/Delta history.
    """
    if ticks < 1:
        raise ValueError("ticks must be >= 1")

    current = deepcopy(world)
    results: list[EnvironmentalContextProcessTick] = []

    for _ in range(ticks):
        before_version = int(current.get("current_version", 0))
        before_tick = int(current.get("current_tick", 0))
        result_version = before_version + 1
        result_tick = before_tick + 1
        updated = deepcopy(current)
        operations: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []

        for rule in _rules(current):
            entity_before = (current.get("entities") or {}).get(rule.entity_id)
            if not isinstance(entity_before, dict) or entity_before.get("status") != "active":
                raise ValueError("context process entity must exist and be active")

            component_before = (
                (entity_before.get("components") or {}).get(rule.state_component) or {}
            )
            last_tick = int(
                component_before.get(
                    "last_transition_tick",
                    entity_before.get("created_at_tick", 0) or 0,
                )
            )
            if result_tick - last_tick < rule.min_ticks:
                continue

            phase_id = str(component_before.get(rule.phase_field) or "")
            phases = {item.phase_id: item for item in rule.phases}
            phase = phases.get(phase_id)
            if phase is None:
                raise ValueError("context process phase is not declared by rule")

            operations.extend(
                deepcopy(_apply_route_overrides(updated, phase.route_overrides))
            )

            entity = updated["entities"][rule.entity_id]
            component = entity.setdefault("components", {}).setdefault(
                rule.state_component,
                {},
            )
            generation = int(component.get("generation", 0)) + 1
            component[rule.phase_field] = phase.next_phase_id
            component["last_action_id"] = phase.action_id
            component["last_transition_tick"] = result_tick
            component["generation"] = generation
            entity["version"] = result_version
            operations.append(
                {
                    "op": "set",
                    "path": (
                        f"/entities/{rule.entity_id}/components/"
                        f"{rule.state_component}"
                    ),
                    "value": deepcopy(component),
                }
            )

            trace_seed = "|".join(
                (
                    rule.entity_id,
                    rule.rule_id,
                    phase.phase_id,
                    phase.action_id,
                    phase.next_phase_id,
                    str(result_tick),
                )
            )
            trace_id = "context_process_trace_" + sha256(
                trace_seed.encode("utf-8")
            ).hexdigest()[:16]
            trace = {
                "entity_id": trace_id,
                "class": "environment_trace",
                "type": "environmental_context_process",
                "status": "active",
                "version": result_version,
                "created_at_tick": result_tick,
                "components": {
                    "transform": deepcopy(
                        (entity.get("components") or {}).get("transform") or {}
                    ),
                    "origin": {
                        "entity_id": rule.entity_id,
                        "rule_id": rule.rule_id,
                        "phase_id": phase.phase_id,
                        "action_id": phase.action_id,
                        "next_phase_id": phase.next_phase_id,
                        "generation": generation,
                    },
                    "route_overrides": tuple(deepcopy(phase.route_overrides)),
                },
            }
            updated.setdefault("entities", {})[trace_id] = trace
            operations.append(
                {
                    "op": "add",
                    "path": f"/entities/{trace_id}",
                    "value": deepcopy(trace),
                }
            )

            transitions.append(
                {
                    "entity_id": rule.entity_id,
                    "rule_id": rule.rule_id,
                    "phase_id": phase.phase_id,
                    "action_id": phase.action_id,
                    "next_phase_id": phase.next_phase_id,
                    "route_overrides": tuple(deepcopy(phase.route_overrides)),
                    "trace_id": trace_id,
                    "generation": generation,
                }
            )

        delta_id = f"delta_{result_version:08d}"
        event_id = f"event_{result_tick:08d}_environment_context_process"
        delta = {
            "delta_id": delta_id,
            "base_version": before_version,
            "result_version": result_version,
            "tick_id": result_tick,
            "operations": deepcopy(operations),
            "provenance": {
                "origin": "environmental-context-process-runtime",
            },
        }
        event = {
            "event_id": event_id,
            "tick_id": result_tick,
            "type": "environmental_context_process_tick",
            "actor": transitions[0]["entity_id"] if len(transitions) == 1 else None,
            "targets": [item["entity_id"] for item in transitions],
            "transitions": deepcopy(transitions),
            "before": {
                "version": before_version,
                "tick": before_tick,
            },
            "after": {
                "version": result_version,
                "tick": result_tick,
                "transition_count": len(transitions),
            },
            "delta_id": delta_id,
            "provenance": {
                "origin": "environmental-context-process-runtime",
                "processed_by": "environmental-context-process-runtime",
            },
        }

        updated.setdefault("deltas", {})[delta_id] = deepcopy(delta)
        updated.setdefault("events", {})[event_id] = deepcopy(event)
        updated.setdefault("versions", {})[str(result_version)] = {
            "parent_version": before_version,
            "delta_id": delta_id,
        }
        updated["current_version"] = result_version
        updated["current_tick"] = result_tick

        current = updated
        results.append(
            EnvironmentalContextProcessTick(
                world=deepcopy(updated),
                event=event,
                delta=delta,
                transitions=tuple(deepcopy(transitions)),
            )
        )

    return tuple(results)
