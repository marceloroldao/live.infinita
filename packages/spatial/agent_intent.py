from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .cold_store import FileRegionColdStore


class AgentIntentError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedIntent:
    intent_type: str
    actor_entity_id: str | None
    operations: tuple[dict[str, Any], ...]
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "actor_entity_id": self.actor_entity_id,
            "operations": [deepcopy(row) for row in self.operations],
            "rationale": self.rationale,
        }


class AgentIntentResolver:
    """Translate semantic agent intents into canonical world operations.

    The resolver is deterministic and does not mutate world state. It is not an
    authorization boundary; resolved operations must still pass MutationGate.

    Supported intents v1:
      move_to_entity
      move_to_position
      establish_relation
      clear_relation
      set_environment
      transfer_possession
    """

    SUPPORTED = frozenset({
        "move_to_entity",
        "move_to_position",
        "establish_relation",
        "clear_relation",
        "set_environment",
        "transfer_possession",
    })

    def __init__(self, store: FileRegionColdStore) -> None:
        self.store = store

    @staticmethod
    def _required(value: Any, field: str) -> str:
        result = str(value or "").strip()
        if not result:
            raise AgentIntentError(f"{field} is required")
        return result

    def _entity(self, entity_id: str) -> dict[str, Any]:
        entity = self.store.get_entity(entity_id)
        if entity is None:
            raise AgentIntentError(f"entity not found: {entity_id}")
        return entity

    @staticmethod
    def _position(value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            raise AgentIntentError("position is required")
        try:
            return {"x": float(value["x"]), "y": float(value["y"])}
        except (KeyError, TypeError, ValueError) as exc:
            raise AgentIntentError("position requires numeric x/y") from exc

    def resolve(self, intent: dict[str, Any]) -> ResolvedIntent:
        if not isinstance(intent, dict):
            raise AgentIntentError("intent must be an object")
        intent_type = str(intent.get("intent") or intent.get("type") or "").strip().lower()
        if intent_type not in self.SUPPORTED:
            raise AgentIntentError(f"unsupported intent: {intent_type}")

        if intent_type == "move_to_entity":
            actor_id = self._required(intent.get("actor_entity_id"), "actor_entity_id")
            target_id = self._required(intent.get("target_entity_id"), "target_entity_id")
            self._entity(actor_id)
            target = self._entity(target_id)
            position = self._position(target.get("position"))
            region_id = self._required(target.get("region_id"), "target.region_id")
            return ResolvedIntent(
                intent_type,
                actor_id,
                ({"op": "move", "entity_id": actor_id, "position": position, "region_id": region_id},),
                f"move {actor_id} to entity {target_id}",
            )

        if intent_type == "move_to_position":
            actor_id = self._required(intent.get("actor_entity_id"), "actor_entity_id")
            actor = self._entity(actor_id)
            position = self._position(intent.get("position"))
            region_id = str(intent.get("region_id") or actor.get("region_id") or "").strip()
            if not region_id:
                raise AgentIntentError("region_id is required")
            return ResolvedIntent(
                intent_type,
                actor_id,
                ({"op": "move", "entity_id": actor_id, "position": position, "region_id": region_id},),
                f"move {actor_id} to explicit position",
            )

        if intent_type in {"establish_relation", "clear_relation"}:
            actor_id = self._required(intent.get("actor_entity_id"), "actor_entity_id")
            target_id = self._required(intent.get("target_entity_id"), "target_entity_id")
            relation = self._required(intent.get("relation"), "relation")
            self._entity(actor_id)
            self._entity(target_id)
            op = "link" if intent_type == "establish_relation" else "unlink"
            return ResolvedIntent(
                intent_type,
                actor_id,
                ({"op": op, "entity_id": actor_id, "relation": relation, "target_id": target_id},),
                f"{op} {actor_id} {relation} {target_id}",
            )

        if intent_type == "set_environment":
            key = self._required(intent.get("key"), "key")
            if key not in {"period", "weather", "biome", "atmosphere_intensity"}:
                raise AgentIntentError(f"environment key not allowed: {key}")
            return ResolvedIntent(
                intent_type,
                None,
                ({"op": "set_world", "path": ["environment", key], "value": deepcopy(intent.get("value"))},),
                f"set environment.{key}",
            )

        # transfer_possession: ownership is represented both as a stable property
        # and a relation so query/navigation code can use either representation.
        actor_id = self._required(intent.get("actor_entity_id"), "actor_entity_id")
        object_id = self._required(intent.get("object_entity_id"), "object_entity_id")
        recipient_id = self._required(intent.get("recipient_entity_id"), "recipient_entity_id")
        self._entity(actor_id)
        self._entity(object_id)
        self._entity(recipient_id)
        return ResolvedIntent(
            intent_type,
            actor_id,
            (
                {"op": "set", "entity_id": object_id, "path": ["properties", "owner_entity_id"], "value": recipient_id},
                {"op": "link", "entity_id": recipient_id, "relation": "owns", "target_id": object_id},
            ),
            f"transfer {object_id} from intent actor {actor_id} to {recipient_id}",
        )
