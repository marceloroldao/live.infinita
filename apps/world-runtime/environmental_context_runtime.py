from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EnvironmentalContextTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    constraints: tuple[dict[str, Any], ...]


def _apply_route_override(
    world: dict[str, Any],
    *,
    region_id: str,
    route_id: str,
    available: bool,
) -> dict[str, Any]:
    region = (world.get("regions") or {}).get(region_id)
    if not isinstance(region, dict):
        raise ValueError("context constraint references missing region")

    routes = region.get("environmental_routes") or ()
    for index, route in enumerate(routes):
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
    raise ValueError("context constraint references missing route")


def apply_environmental_context_constraints(
    world: dict[str, Any],
) -> EnvironmentalContextTick:
    """Apply world-owned contextual physical constraints before Water evolves.

    Context is read from entity state declared by World State. The runtime has no
    observer, Memoria.ia, or temporal-evidence dependency.
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
                "environmental_route_constraints",
                (),
            )
        ),
        key=lambda item: str((item or {}).get("rule_id") or ""),
    )

    for rule in rules:
        rule_id = str((rule or {}).get("rule_id") or "")
        entity_id = str((rule or {}).get("entity") or "")
        source_component = str((rule or {}).get("source_component") or "")
        source_field = str((rule or {}).get("source_field") or "")
        if not rule_id or not entity_id or not source_component or not source_field:
            raise ValueError("context constraint rule is incomplete")

        entity = (updated.get("entities") or {}).get(entity_id)
        if not isinstance(entity, dict) or entity.get("status") != "active":
            raise ValueError("context constraint entity must exist and be active")

        component = ((entity.get("components") or {}).get(source_component) or {})
        state_id = str(component.get(source_field) or "")
        if not state_id:
            raise ValueError("context constraint source state is missing")

        states = (rule or {}).get("states") or {}
        state = states.get(state_id)
        if not isinstance(state, dict):
            raise ValueError("context constraint state is not declared")

        overrides = tuple(deepcopy(state.get("route_overrides") or ()))
        if not overrides:
            raise ValueError("context constraint state requires route overrides")

        normalized: list[dict[str, Any]] = []
        for override in overrides:
            region_id = str((override or {}).get("region_id") or "")
            route_id = str((override or {}).get("route_id") or "")
            available = (override or {}).get("available")
            if not region_id or not route_id or not isinstance(available, bool):
                raise ValueError(
                    "context route override requires region_id, route_id and bool available"
                )
            operations.append(
                _apply_route_override(
                    updated,
                    region_id=region_id,
                    route_id=route_id,
                    available=available,
                )
            )
            normalized.append(
                {
                    "region_id": region_id,
                    "route_id": route_id,
                    "available": available,
                }
            )

        applied.append(
            {
                "rule_id": rule_id,
                "entity_id": entity_id,
                "state_id": state_id,
                "route_overrides": tuple(normalized),
            }
        )

    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_environment_context"
    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": deepcopy(operations),
        "provenance": {
            "origin": "environmental-context-runtime",
        },
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "environmental_context_applied",
        "actor": None,
        "targets": sorted({item["entity_id"] for item in applied}),
        "constraints": deepcopy(applied),
        "before": {
            "version": before_version,
            "tick": before_tick,
        },
        "after": {
            "version": result_version,
            "tick": result_tick,
            "constraint_count": len(applied),
        },
        "delta_id": delta_id,
        "provenance": {
            "origin": "environmental-context-runtime",
            "processed_by": "environmental-context-runtime",
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

    return EnvironmentalContextTick(
        world=updated,
        event=event,
        delta=delta,
        constraints=tuple(applied),
    )
