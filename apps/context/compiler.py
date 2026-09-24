from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable


CONTEXT_SCHEMA_VERSION = "1.1"


@dataclass(frozen=True)
class ContextPackage:
    payload: dict[str, Any]
    digest: str

    @property
    def world_version(self) -> int:
        return int(self.payload["world"]["version"])

    @property
    def world_sequence(self) -> int:
        return int(self.payload["world"]["sequence"])

    @property
    def world_state_hash(self) -> str:
        return str(self.payload["world"].get("state_hash") or "")

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload, "context_digest": self.digest}


class ContextCompiler:
    """Build a bounded, deterministic, read-only package for probabilistic operators.

    The compiler accepts either resident world entities or an explicitly supplied
    bounded entity slice. The latter is used by Live.infinita's cold spatial
    runtime so a Context Package never requires rehydrating the whole universe.
    """

    def __init__(self, *, max_entities: int = 64, max_regions: int = 32) -> None:
        if max_entities < 1:
            raise ValueError("max_entities precisa ser >= 1")
        if max_regions < 1:
            raise ValueError("max_regions precisa ser >= 1")
        self.max_entities = int(max_entities)
        self.max_regions = int(max_regions)

    def compile(
        self,
        *,
        world: dict[str, Any],
        actor: dict[str, Any] | None = None,
        bound_entity_id: str | None = None,
        entities: Iterable[dict[str, Any]] | None = None,
        entities_total: int | None = None,
        scope: dict[str, Any] | None = None,
    ) -> ContextPackage:
        source_entities = entities if entities is not None else world.get("entities", [])
        compact_entities = sorted(
            (self._compact_entity(item) for item in source_entities if isinstance(item, dict)),
            key=lambda item: str(item.get("id") or ""),
        )
        supplied_entities = len(compact_entities)
        visible_entities = compact_entities[: self.max_entities]
        total_entities = max(
            supplied_entities,
            int(entities_total if entities_total is not None else supplied_entities),
        )

        bound_entity = None
        if bound_entity_id:
            bound_entity = next(
                (item for item in compact_entities if item.get("id") == bound_entity_id),
                None,
            )

        actor_view = self._compact_actor(actor) if actor else None
        binding_status = "unbound"
        if bound_entity_id:
            binding_status = "active" if bound_entity is not None else "outside_context_slice"

        regions = sorted(
            (self._compact_region(item) for item in world.get("regions", []) if isinstance(item, dict)),
            key=lambda item: str(item.get("id") or ""),
        )[: self.max_regions]

        payload: dict[str, Any] = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "authority": "read-only-context",
            "world": {
                "world_id": world.get("world_id"),
                "title": world.get("title"),
                "version": int(world.get("version", 0)),
                "sequence": int(world.get("sequence", 0)),
                "state_hash": world.get("state_hash"),
                "environment": dict(world.get("environment") or {}),
                "story": dict(world.get("story") or {}),
                "regions": regions,
                "entities": visible_entities,
                "entities_in_slice": supplied_entities,
                "entities_total": total_entities,
                "entities_truncated": supplied_entities > len(visible_entities),
            },
            "scope": dict(scope or {"mode": "resident-world"}),
            "actor": actor_view,
            "binding": {
                "status": binding_status,
                "entity_id": bound_entity_id,
                "entity": bound_entity,
            },
            "policy": {
                "llm_may_propose_only": True,
                "direct_world_write": False,
                "commit_requires_validator": True,
                "proposal_must_match_world_revision": True,
            },
        }
        digest = hashlib.sha256(self._canonical_bytes(payload)).hexdigest()
        return ContextPackage(payload=payload, digest=digest)

    @staticmethod
    def _compact_entity(entity: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": entity.get("id"),
            "type": entity.get("type"),
            "region_id": entity.get("region_id"),
            "position": dict(entity.get("position") or {}),
            "scale": entity.get("scale"),
            "properties": dict(entity.get("properties") or {}),
        }

    @staticmethod
    def _compact_region(region: dict[str, Any]) -> dict[str, Any]:
        metadata = region.get("metadata") if isinstance(region.get("metadata"), dict) else {}
        return {
            "id": region.get("id"),
            "biome": region.get("biome"),
            "metadata": {
                key: metadata.get(key)
                for key in ("label", "description")
                if metadata.get(key) is not None
            },
        }

    @staticmethod
    def _compact_actor(actor: dict[str, Any]) -> dict[str, Any]:
        return {
            "actor_key": actor.get("actor_key"),
            "source": actor.get("source"),
            "actor_id": actor.get("actor_id"),
            "display_name": actor.get("display_name"),
            "first_seen_unix": actor.get("first_seen_unix"),
            "last_seen_unix": actor.get("last_seen_unix"),
            "interactions_total": actor.get("interactions_total", 0),
            "interactions_by_kind": dict(actor.get("interactions_by_kind") or {}),
            "last_interaction": actor.get("last_interaction"),
        }

    @staticmethod
    def _canonical_bytes(value: dict[str, Any]) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
