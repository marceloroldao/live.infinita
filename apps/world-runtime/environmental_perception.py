from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


def _region(entity: dict[str, Any]) -> str | None:
    value = ((entity.get("components") or {}).get("transform") or {}).get("region_id")
    return str(value) if value is not None else None


def project_environmental_presence(
    world: dict[str, Any],
    observer_id: str,
) -> dict[str, Any]:
    """Return a read-only cognitive projection of co-located environmental agents.

    The authoritative world is never mutated. Presence relations exist only in the
    observer's cognitive projection and are regenerated deterministically from spatial
    state on every request.
    """
    projected = deepcopy(world)
    entities = projected.get("entities") or {}
    observer = entities.get(observer_id)
    if not isinstance(observer, dict) or observer.get("status") != "active":
        return projected

    observer_region = _region(observer)
    if observer_region is None:
        return projected

    relations = projected.setdefault("relations", {})
    for entity_id in sorted(entities):
        if entity_id == observer_id:
            continue
        entity = entities[entity_id]
        if (
            not isinstance(entity, dict)
            or entity.get("status") != "active"
            or entity.get("class") != "environmental_agent"
            or _region(entity) != observer_region
        ):
            continue

        digest = sha256(f"{observer_id}|{entity_id}|environmental-presence".encode("utf-8")).hexdigest()[:16]
        relation_id = f"rel_env_presence_{digest}"
        relations[relation_id] = {
            "relation_id": relation_id,
            "subject": observer_id,
            "predicate": "co_located_with",
            "object": entity_id,
            "status": "active",
            "confidence": 1.0,
            "valid_from_tick": int(projected.get("current_tick", 0)),
            "valid_until_tick": None,
            "source": {"type": "environmental-presence-projection"},
            "version": int(projected.get("current_version", 0)),
        }

    return projected
