from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.spatial import Region, RegionCatalog, RegionEntityIndex, RegionSpatialGrid, SpatialResolver


class SpatialSession:
    """Observer-local projection of the authoritative global World State.

    Indexed worlds use region-local entity candidates plus a spatial grid for
    position -> region lookup. Legacy worlds remain backward compatible.
    """

    def __init__(self, resolver: SpatialResolver | None = None) -> None:
        self.resolver = resolver or SpatialResolver()
        self._catalog: RegionCatalog | None = None
        self._index: RegionEntityIndex | None = None
        self._region_grid: RegionSpatialGrid | None = None
        self._index_sequence: int | None = None

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
    def _indexed_world(world: dict[str, Any]) -> bool:
        entities = [row for row in world.get("entities", []) if isinstance(row, dict)]
        regions = [row for row in world.get("regions", []) if isinstance(row, dict)]
        return bool(
            entities
            and regions
            and all(str(row.get("region_id", "")).strip() for row in entities)
            and all(str(row.get("id", "")).strip() for row in regions)
        )

    @staticmethod
    def _catalog_from_world(world: dict[str, Any]) -> RegionCatalog:
        rows: list[Region] = []
        for row in world.get("regions", []):
            if not isinstance(row, dict):
                continue
            center = row.get("center", {}) if isinstance(row.get("center"), dict) else {}
            rows.append(
                Region(
                    id=str(row.get("id", "")),
                    center=(float(center.get("x", 0.0)), float(center.get("y", 0.0))),
                    radius=float(row.get("radius", 1.0) or 1.0),
                    biome=str(row.get("biome", "unknown")),
                    neighbors=tuple(str(value) for value in row.get("neighbors", []) if str(value)),
                    metadata=dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {},
                )
            )
        return RegionCatalog(rows)

    def _rebuild_index(self, world: dict[str, Any]) -> None:
        entities = [row for row in world.get("entities", []) if isinstance(row, dict)]
        self._catalog = self._catalog_from_world(world)
        self._index = RegionEntityIndex(entities)
        self._region_grid = RegionSpatialGrid(self._catalog.all())
        self._index_sequence = int(world.get("sequence", 0))

    @staticmethod
    def _find_world_entity(world: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
        for entity in world.get("entities", []):
            if isinstance(entity, dict) and str(entity.get("id", "")) == entity_id:
                return entity
        return None

    def _sync_index_from_delta(self, world: dict[str, Any], delta: dict[str, Any] | None) -> None:
        if self._index is None or self._catalog is None or self._region_grid is None:
            self._rebuild_index(world)
            return
        sequence = int(world.get("sequence", 0))
        if sequence == self._index_sequence:
            return
        if not isinstance(delta, dict):
            self._rebuild_index(world)
            return

        operations = delta.get("operations", [])
        if not isinstance(operations, list):
            self._rebuild_index(world)
            return

        affected: set[str] = set()
        rebuild = False
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            op = operation.get("op")
            if op == "replace_world_from_bootstrap":
                rebuild = True
                break
            if op == "append_entity" and isinstance(operation.get("value"), dict):
                value = operation["value"]
                if str(value.get("region_id", "")).strip():
                    self._index.upsert(value)
                else:
                    rebuild = True
                    break
                continue
            if op == "set":
                path = operation.get("path", [])
                if isinstance(path, list) and len(path) >= 2 and path[0] == "entities":
                    affected.add(str(path[1]))
                elif isinstance(path, list) and path and path[0] == "regions":
                    rebuild = True
                    break

        if rebuild:
            self._rebuild_index(world)
            return
        for entity_id in affected:
            entity = self._find_world_entity(world, entity_id)
            if entity is None:
                self._index.remove(entity_id)
            elif str(entity.get("region_id", "")).strip():
                self._index.upsert(entity)
            else:
                self._rebuild_index(world)
                return
        self._index_sequence = sequence

    def resolve_observer(self, world: dict[str, Any], view: dict[str, Any]) -> dict[str, float]:
        entity_id = str(view.get("observer_entity_id") or "").strip()
        if entity_id and self._index is not None:
            entity = self._index.get(entity_id)
            if entity is not None and isinstance(entity.get("position"), dict):
                return {
                    "x": float(entity["position"].get("x", 0.0)),
                    "y": float(entity["position"].get("y", 0.0)),
                }
        if entity_id:
            entity = self._find_world_entity(world, entity_id)
            if entity is not None and isinstance(entity.get("position"), dict):
                return {
                    "x": float(entity["position"].get("x", 0.0)),
                    "y": float(entity["position"].get("y", 0.0)),
                }
        fallback = view.get("position", {})
        return {
            "x": float(fallback.get("x", 0.0)),
            "y": float(fallback.get("y", 0.0)),
        }

    def _locate_region(self, observer: dict[str, float], view: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        entity_id = str(view.get("observer_entity_id") or "").strip()
        if entity_id and self._index is not None:
            region_id = self._index.region_for_entity(entity_id)
            if region_id:
                return region_id, {"mode": "entity_region_index", "region_candidates_examined": 1}
        if self._region_grid is not None:
            result = self._region_grid.lookup(observer["x"], observer["y"])
            return result.region_id, {
                "mode": "region_spatial_grid",
                "region_candidates_examined": result.candidates_examined,
                "region_cell": [result.cell[0], result.cell[1]],
            }
        return None, {"mode": "region_unresolved", "region_candidates_examined": 0}

    def build(
        self,
        world: dict[str, Any],
        view: dict[str, Any],
        *,
        delta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        all_entities = [entity for entity in world.get("entities", []) if isinstance(entity, dict)]
        all_regions = [region for region in world.get("regions", []) if isinstance(region, dict)]
        indexed = self._indexed_world(world)

        candidates = all_entities
        candidate_regions = all_regions
        candidate_meta = {
            "mode": "legacy_global_scan",
            "candidates_examined": len(all_entities),
            "candidate_region_ids": [],
            "region_lookup_mode": "legacy_global_scan",
            "region_candidates_examined": len(all_regions),
        }

        if indexed:
            if self._index is None or self._catalog is None or self._region_grid is None:
                self._rebuild_index(world)
            else:
                self._sync_index_from_delta(world, delta)
            observer = self.resolve_observer(world, view)
            current_region_id, region_lookup = self._locate_region(observer, view)
            if current_region_id and self._index is not None and self._catalog is not None:
                query = self._index.candidates(
                    catalog=self._catalog,
                    current_region_id=current_region_id,
                    include_neighbor_depth=1,
                )
                candidates = query["entities"]
                region_ids = set(query["region_ids"])
                candidate_regions = [row for row in all_regions if str(row.get("id", "")) in region_ids]
                candidate_meta = {
                    "mode": "region_entity_index",
                    "current_region_id": current_region_id,
                    "candidates_examined": int(query["candidates_examined"]),
                    "candidate_region_ids": query["region_ids"],
                    "indexed_entities_total": self._index.size(),
                    "region_lookup_mode": region_lookup["mode"],
                    "region_candidates_examined": region_lookup["region_candidates_examined"],
                    **({"region_cell": region_lookup["region_cell"]} if "region_cell" in region_lookup else {}),
                }
        else:
            observer = self.resolve_observer(world, view)

        interest = self.resolver.resolve(
            observer={"position": observer},
            direction=dict(view.get("direction", {})),
            entities=candidates,
            regions=candidate_regions,
        )
        hot_ids = set(interest["hot"]["entity_ids"])
        warm_ids = set(interest["warm"]["entity_ids"])
        hot_entities = [deepcopy(entity) for entity in candidates if str(entity.get("id", "")) in hot_ids]
        warm_entities = [
            {
                "id": str(entity.get("id", "")),
                "type": str(entity.get("type", "")),
                "position": deepcopy(entity.get("position", {})),
            }
            for entity in candidates
            if str(entity.get("id", "")) in warm_ids
        ]

        local = {key: deepcopy(value) for key, value in world.items() if key not in {"entities", "regions"}}
        local["entities"] = hot_entities
        local["interest"] = {
            **interest,
            **candidate_meta,
            "observer_entity_id": view.get("observer_entity_id"),
            "warm_entities": warm_entities,
            "source_entities_total": len(all_entities),
            "source_regions_total": len(all_regions),
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
        delta = message.get("delta") if isinstance(message.get("delta"), dict) else None
        if self._indexed_world(message["world"]):
            if self._index is None or self._catalog is None or self._region_grid is None:
                self._rebuild_index(message["world"])
            else:
                self._sync_index_from_delta(message["world"], delta)
        observer = self.resolve_observer(message["world"], view)
        wrapped["world"] = self.build(message["world"], view, delta=delta)
        interest = wrapped["world"].get("interest", {})
        wrapped["delivery"] = {
            "mode": "local_world_slice",
            "observer_entity_id": view.get("observer_entity_id"),
            "observer": observer,
            "candidate_mode": interest.get("mode", "legacy_global_scan"),
            "candidates_examined": interest.get("candidates_examined", 0),
            "region_lookup_mode": interest.get("region_lookup_mode", "legacy_global_scan"),
            "region_candidates_examined": interest.get("region_candidates_examined", 0),
        }
        return wrapped
