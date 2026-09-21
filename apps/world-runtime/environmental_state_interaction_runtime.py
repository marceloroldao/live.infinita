from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EnvironmentalStateInteractionTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    interactions: tuple[dict[str, Any], ...]


def _read_input(world: dict[str, Any], source: dict[str, Any]) -> tuple[str, str]:
    input_id = str((source or {}).get("input_id") or "")
    entity_id = str((source or {}).get("entity") or "")
    component_id = str((source or {}).get("component") or "")
    field_id = str((source or {}).get("field") or "")
    if not input_id or not entity_id or not component_id or not field_id:
        raise ValueError("state interaction input is incomplete")

    entity = (world.get("entities") or {}).get(entity_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        raise ValueError("state interaction input entity must exist and be active")
    component = ((entity.get("components") or {}).get(component_id) or {})
    value = component.get(field_id)
    if value is None:
        raise ValueError("state interaction input field is missing")
    return input_id, str(value)


def _apply_route_override(
    world: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    region_id = str((override or {}).get("region_id") or "")
    route_id = str((override or {}).get("route_id") or "")
    available = (override or {}).get("available")
    if not region_id or not route_id or not isinstance(available, bool):
        raise ValueError(
            "state interaction route override requires region_id, route_id and bool available"
        )

    region = (world.get("regions") or {}).get(region_id)
    if not isinstance(region, dict):
        raise ValueError("state interaction override references missing region")
    for index, route in enumerate(region.get("environmental_routes") or ()):
        if str((route or {}).get("route_id") or "") == route_id:
            route["available"] = available
            return {
                "op": "set",
                "path": (
                    f"/regions/{region_id}/environmental_routes/"
                    f"{index}/available"
                ),
                "value": available,
            }
    raise ValueError("state interaction override references missing route")


def apply_environmental_state_interactions(
    world: dict[str, Any],
) -> EnvironmentalStateInteractionTick:
    """Apply world-declared interactions among multiple current entity states.

    The runtime is table-driven and has no XOR, semantic, observer, Memoria.ia or
    temporal-learning logic. It reads exact World-State values, matches one declared
    case, applies that case's physical overrides, and records the transaction.
    """
    before_version = int(world.get("current_version", 0))
    before_tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = before_tick + 1

    updated = deepcopy(world)
    operations: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []

    rules = sorted(
        (
            deepcopy(raw)
            for raw in (world.get("rules") or {}).get(
                "environmental_state_interactions",
                (),
            )
        ),
        key=lambda item: str((item or {}).get("rule_id") or ""),
    )
    if not rules:
        raise ValueError("world declares no environmental state interactions")

    for rule in rules:
        rule_id = str((rule or {}).get("rule_id") or "")
        if not rule_id:
            raise ValueError("state interaction rule requires rule_id")

        values = dict(
            _read_input(world, source)
            for source in (rule or {}).get("inputs") or ()
        )
        if len(values) < 2:
            raise ValueError("state interaction requires at least two inputs")

        matched = None
        for case in (rule or {}).get("cases") or ():
            expected = {
                str(key): str(value)
                for key, value in ((case or {}).get("when") or {}).items()
            }
            if expected == values:
                matched = deepcopy(case)
                break
        if not isinstance(matched, dict):
            raise ValueError("state interaction has no case for current input state")

        case_id = str(matched.get("case_id") or "")
        overrides = tuple(deepcopy(matched.get("route_overrides") or ()))
        if not case_id or not overrides:
            raise ValueError("state interaction case requires case_id and route_overrides")

        normalized: list[dict[str, Any]] = []
        for override in overrides:
            operations.append(_apply_route_override(updated, override))
            normalized.append(
                {
                    "region_id": str(override["region_id"]),
                    "route_id": str(override["route_id"]),
                    "available": bool(override["available"]),
                }
            )

        applied.append(
            {
                "rule_id": rule_id,
                "case_id": case_id,
                "inputs": dict(sorted(values.items())),
                "route_overrides": tuple(normalized),
            }
        )

    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_environment_state_interaction"
    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": deepcopy(operations),
        "provenance": {
            "origin": "environmental-state-interaction-runtime",
        },
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "environmental_state_interaction_applied",
        "actor": None,
        "targets": [],
        "interactions": deepcopy(applied),
        "before": {
            "version": before_version,
            "tick": before_tick,
        },
        "after": {
            "version": result_version,
            "tick": result_tick,
            "interaction_count": len(applied),
        },
        "delta_id": delta_id,
        "provenance": {
            "origin": "environmental-state-interaction-runtime",
            "processed_by": "environmental-state-interaction-runtime",
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

    return EnvironmentalStateInteractionTick(
        world=updated,
        event=event,
        delta=delta,
        interactions=tuple(applied),
    )
