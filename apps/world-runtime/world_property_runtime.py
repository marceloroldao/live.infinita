from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


def update_environmental_route_properties(
    world: dict[str, Any],
    *,
    region_id: str,
    route_id: str,
    properties: Mapping[str, int | float],
) -> dict[str, Any]:
    """Authoritatively replace local route properties and record Event/Delta.

    This is generic world configuration state. No property name has built-in meaning.
    """
    if not region_id or not route_id:
        raise ValueError("region_id and route_id must be non-empty")
    if not properties:
        raise ValueError("properties must be non-empty")
    normalized: dict[str, int | float] = {}
    for key, value in properties.items():
        property_id = str(key)
        if not property_id:
            raise ValueError("property id must be non-empty")
        if not isinstance(value, (int, float)):
            raise ValueError("route properties must be numeric")
        normalized[property_id] = value

    region = (world.get("regions") or {}).get(region_id)
    if not isinstance(region, dict):
        raise ValueError("unknown region_id")
    routes = region.get("environmental_routes") or ()
    index = next(
        (i for i, route in enumerate(routes) if str((route or {}).get("route_id") or "") == route_id),
        None,
    )
    if index is None:
        raise ValueError("unknown route_id")

    before_version = int(world.get("current_version", 0))
    before_tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = before_tick + 1

    updated = deepcopy(world)
    target = updated["regions"][region_id]["environmental_routes"][index]
    previous = deepcopy(target.get("properties") or {})
    target["properties"] = deepcopy(normalized)

    suffix = sha256(
        f"{region_id}|{route_id}|{result_tick}|{sorted(normalized.items())}".encode("utf-8")
    ).hexdigest()[:16]
    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_route_properties_{suffix}"

    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": [
            {
                "op": "set",
                "path": f"/regions/{region_id}/environmental_routes/{index}/properties",
                "value": deepcopy(normalized),
            }
        ],
        "provenance": {
            "origin": "world-property-runtime",
            "region_id": region_id,
            "route_id": route_id,
        },
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "environmental_route_properties_changed",
        "actor": None,
        "targets": [],
        "before": {
            "version": before_version,
            "tick": before_tick,
            "properties": previous,
        },
        "after": {
            "version": result_version,
            "tick": result_tick,
            "properties": deepcopy(normalized),
        },
        "region_id": region_id,
        "route_id": route_id,
        "delta_id": delta_id,
        "provenance": {
            "origin": "world-property-runtime",
            "processed_by": "world-property-runtime",
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
    return updated
