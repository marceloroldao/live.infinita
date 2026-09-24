from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .cold_store import FileRegionColdStore


class ColdMutationError(ValueError):
    pass


class ColdEntityMutator:
    """Generic deterministic mutation layer for cold-backed entities.

    Supported canonical operations:
      create: {op, entity}
      set:    {op, entity_id, path, value}
      move:   {op, entity_id, position, region_id?}
      remove: {op, entity_id}
      link:   {op, entity_id, relation, target_id}
      unlink: {op, entity_id, relation, target_id}

    Relations are stored as sorted unique ids under entity['relations'][relation].
    """

    def __init__(self, store: FileRegionColdStore) -> None:
        self.store = store

    @staticmethod
    def _id(value: Any, field: str) -> str:
        result = str(value or "").strip()
        if not result:
            raise ColdMutationError(f"{field} is required")
        return result

    @staticmethod
    def _path(value: Any) -> list[str]:
        if isinstance(value, str):
            parts = [part for part in value.split(".") if part]
        elif isinstance(value, list):
            parts = [str(part) for part in value if str(part)]
        else:
            parts = []
        if not parts:
            raise ColdMutationError("path is required")
        if parts[0] in {"id"}:
            raise ColdMutationError("entity id is immutable")
        return parts

    @staticmethod
    def _set_nested(entity: dict[str, Any], path: list[str], value: Any) -> None:
        cursor: Any = entity
        for key in path[:-1]:
            if not isinstance(cursor, dict):
                raise ColdMutationError("invalid set path")
            child = cursor.get(key)
            if child is None:
                cursor[key] = {}
                child = cursor[key]
            if not isinstance(child, dict):
                raise ColdMutationError("invalid set path")
            cursor = child
        if not isinstance(cursor, dict):
            raise ColdMutationError("invalid set path")
        cursor[path[-1]] = deepcopy(value)

    def _require_entity(self, entity_id: str) -> dict[str, Any]:
        entity = self.store.get_entity(entity_id)
        if entity is None:
            raise ColdMutationError(f"entity not found: {entity_id}")
        return entity

    def normalize(self, operation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(operation, dict):
            raise ColdMutationError("operation must be an object")
        op = str(operation.get("op") or "").strip().lower()
        if op == "create":
            entity = deepcopy(operation.get("entity"))
            if not isinstance(entity, dict):
                raise ColdMutationError("create.entity is required")
            entity["id"] = self._id(entity.get("id"), "entity.id")
            entity["region_id"] = self._id(entity.get("region_id"), "entity.region_id")
            return {"op": "create", "entity": entity}
        if op == "set":
            return {
                "op": "set",
                "entity_id": self._id(operation.get("entity_id"), "entity_id"),
                "path": self._path(operation.get("path")),
                "value": deepcopy(operation.get("value")),
            }
        if op == "move":
            position = operation.get("position")
            if not isinstance(position, dict):
                raise ColdMutationError("move.position is required")
            normalized: dict[str, Any] = {
                "op": "move",
                "entity_id": self._id(operation.get("entity_id"), "entity_id"),
                "position": {
                    "x": float(position.get("x", 0.0)),
                    "y": float(position.get("y", 0.0)),
                },
            }
            if operation.get("region_id") is not None:
                normalized["region_id"] = self._id(operation.get("region_id"), "region_id")
            return normalized
        if op == "remove":
            return {"op": "remove", "entity_id": self._id(operation.get("entity_id"), "entity_id")}
        if op in {"link", "unlink"}:
            return {
                "op": op,
                "entity_id": self._id(operation.get("entity_id"), "entity_id"),
                "relation": self._id(operation.get("relation"), "relation"),
                "target_id": self._id(operation.get("target_id"), "target_id"),
            }
        raise ColdMutationError(f"unsupported cold operation: {op}")

    def apply(self, operation: dict[str, Any]) -> dict[str, Any]:
        operation = self.normalize(operation)
        op = operation["op"]

        if op == "create":
            entity = deepcopy(operation["entity"])
            entity_id = entity["id"]
            if self.store.entity_region(entity_id) is not None:
                raise ColdMutationError(f"entity already exists: {entity_id}")
            self.store.upsert(entity)
            return operation

        entity_id = operation["entity_id"]
        if op == "remove":
            if not self.store.remove(entity_id):
                raise ColdMutationError(f"entity not found: {entity_id}")
            return operation

        entity = self._require_entity(entity_id)
        if op == "set":
            self._set_nested(entity, operation["path"], operation["value"])
        elif op == "move":
            entity["position"] = deepcopy(operation["position"])
            if "region_id" in operation:
                entity["region_id"] = operation["region_id"]
        elif op in {"link", "unlink"}:
            relations = entity.setdefault("relations", {})
            if not isinstance(relations, dict):
                raise ColdMutationError("entity relations must be an object")
            relation = operation["relation"]
            current = relations.get(relation, [])
            if not isinstance(current, list):
                raise ColdMutationError("relation value must be a list")
            values = {str(value) for value in current if str(value)}
            if op == "link":
                if self.store.entity_region(operation["target_id"]) is None:
                    raise ColdMutationError(f"target entity not found: {operation['target_id']}")
                values.add(operation["target_id"])
            else:
                values.discard(operation["target_id"])
            relations[relation] = sorted(values)
        else:
            raise ColdMutationError(f"unsupported cold operation: {op}")

        self.store.upsert(entity)
        return operation

    def apply_many(self, operations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.apply(operation) for operation in operations]
