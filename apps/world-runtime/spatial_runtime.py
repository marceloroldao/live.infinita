from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


def relocate_entity(
    world: dict[str, Any],
    entity_id: str,
    region_id: str,
    *,
    close_runtime_observations: bool = True,
) -> dict[str, Any]:
    """Relocate one active entity and record an authoritative spatial transition."""
    if not entity_id or not region_id:
        raise ValueError("entity_id and region_id must be non-empty")

    entity = (world.get("entities") or {}).get(entity_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        raise ValueError("entity must exist and be active")

    before_version = int(world.get("current_version", 0))
    before_tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = before_tick + 1

    updated = deepcopy(world)
    moved = updated["entities"][entity_id]
    transform = moved.setdefault("components", {}).setdefault("transform", {})
    before_region = transform.get("region_id")
    transform["region_id"] = region_id
    moved["version"] = result_version

    operations: list[dict[str, Any]] = [
        {
            "op": "set",
            "path": f"/entities/{entity_id}/components/transform/region_id",
            "value": region_id,
        }
    ]

    if close_runtime_observations:
        for relation_id, relation in updated.setdefault("relations", {}).items():
            source = (relation or {}).get("source") or {}
            if (
                relation.get("status") == "active"
                and relation.get("subject") == entity_id
                and source.get("type") == "world-runtime"
            ):
                relation["status"] = "inactive"
                relation["valid_until_tick"] = result_tick
                relation["version"] = result_version
                operations.append(
                    {
                        "op": "deactivate",
                        "path": f"/relations/{relation_id}",
                    }
                )

    seed = f"{entity_id}|{before_region}|{region_id}|{result_tick}"
    suffix = sha256(seed.encode("utf-8")).hexdigest()[:16]
    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_relocate_{suffix}"

    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": deepcopy(operations),
        "provenance": {"origin": "spatial-runtime", "entity_id": entity_id},
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "entity_relocated",
        "actor": entity_id,
        "targets": [],
        "before": {
            "version": before_version,
            "tick": before_tick,
            "region_id": before_region,
        },
        "after": {
            "version": result_version,
            "tick": result_tick,
            "region_id": region_id,
        },
        "delta_id": delta_id,
        "provenance": {
            "origin": "spatial-runtime",
            "processed_by": "spatial-runtime",
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
