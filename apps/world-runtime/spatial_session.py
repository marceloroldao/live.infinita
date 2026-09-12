from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.spatial import SpatialResolver


class SpatialSession:
    """Observer-local projection of the authoritative global World State.

    This layer never mutates or persists the source world. It only decides what
    a renderer session should receive right now.
    """

    def __init__(self, resolver: SpatialResolver | None = None) -> None:
        self.resolver = resolver or SpatialResolver()

    @staticmethod
    def default_view(world: dict[str, Any]) -> dict[str, Any]:
        for entity in world.get("entities", []):
            if entity.get("type") == "human" and isinstance(entity.get("position"), dict):
                return {
                    "observer_entity_id": str(entity.get("id", "")) or None,
                    "position": dict(entity["position"]),
                    "direction": {"x": 0.0, "y": 0.0},
                    "mode": "local",
                }
        return {
            "observer_entity_id": None,
            "position": {"x": 640.0, "y": 360.0},
            "direction": {"x": 0.0, "y": 0.0},
            "mode": "local",
        }

    @staticmethod
    def normalize_view(message: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        position = message.get("position")
        direction = message.get("direction")
        result = deepcopy(fallback)
        if "observer_entity_id" in message:
            value = str(message.get("observer_entity_id") or "").strip()
            result["observer_entity_id"] = value or None
        if isinstance(position, dict):
            result["position"] = {
                "x": float(position.get("x", result["position"]["x"])),
                "y": float(position.get("y", result["position"]["y"])),
            }
        if isinstance(direction, dict):
            result["direction"] = {
                "x": float(direction.get("x", 0.0)),
                "y": float(direction.get("y", 0.0)),
            }
        result["mode"] = "local"
        return result

    @staticmethod
    def resolve_observer(world: dict[str, Any], view: dict[str, Any]) -> dict[str, float]:
        entity_id = str(view.get("observer_entity_id") or "").strip()
        if entity_id:
            for entity in world.get("entities", []):
                if str(entity.get("id", "")) != entity_id:
                    continue
                position = entity.get("position")
                if isinstance(position, dict):
                    return {
                        "x": float(position.get("x", 0.0)),
                        "y": float(position.get("y", 0.0)),
                    }
        fallback = view.get("position", {})
        return {
            "x": float(fallback.get("x", 0.0)),
            "y": float(fallback.get("y", 0.0)),
        }

    def build(self, world: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
        entities = [entity for entity in world.get("entities", []) if isinstance(entity, dict)]
        regions = [region for region in world.get("regions", []) if isinstance(region, dict)]
        observer = self.resolve_observer(world, view)
        interest = self.resolver.resolve(
            observer={"position": observer},
            direction=dict(view.get("direction", {})),
            entities=entities,
            regions=regions,
        )
        hot_ids = set(interest["hot"]["entity_ids"])
        warm_ids = set(interest["warm"]["entity_ids"])
        hot_entities = [deepcopy(entity) for entity in entities if str(entity.get("id", "")) in hot_ids]
        warm_entities = [
            {
                "id": str(entity.get("id", "")),
                "type": str(entity.get("type", "")),
                "position": deepcopy(entity.get("position", {})),
            }
            for entity in entities
            if str(entity.get("id", "")) in warm_ids
        ]

        local = {
            key: deepcopy(value)
            for key, value in world.items()
            if key not in {"entities", "regions"}
        }
        local["entities"] = hot_entities
        local["interest"] = {
            **interest,
            "observer_entity_id": view.get("observer_entity_id"),
            "warm_entities": warm_entities,
            "source_entities_total": len(entities),
            "materialized_entities_total": len(hot_entities),
        }
        return local

    def wrap_world_message(
        self,
        message: dict[str, Any],
        view: dict[str, Any],
    ) -> dict[str, Any]:
        if message.get("type") != "world_state" or not isinstance(message.get("world"), dict):
            return deepcopy(message)
        wrapped = deepcopy(message)
        observer = self.resolve_observer(message["world"], view)
        wrapped["world"] = self.build(message["world"], view)
        wrapped["delivery"] = {
            "mode": "local_world_slice",
            "observer_entity_id": view.get("observer_entity_id"),
            "observer": observer,
        }
        return wrapped
