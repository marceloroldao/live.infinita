from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .regions import RegionCatalog


class RegionEntityIndex:
    """Deterministic region -> entity candidate index.

    The index keeps cold entities out of resolver input by exposing only the
    current region and a bounded neighborhood. It does not own entity truth;
    callers may rebuild or incrementally update it from persistent storage.
    """

    def __init__(self, entities: Iterable[dict[str, Any]] | None = None) -> None:
        self._by_region: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._entity_region: dict[str, str] = {}
        for entity in entities or []:
            self.upsert(entity)

    def upsert(self, entity: dict[str, Any]) -> None:
        entity_id = str(entity.get("id", "")).strip()
        region_id = str(entity.get("region_id", "")).strip()
        if not entity_id:
            raise ValueError("entity id is required")
        if not region_id:
            raise ValueError("entity region_id is required")
        previous_region = self._entity_region.get(entity_id)
        if previous_region and previous_region != region_id:
            self._by_region.get(previous_region, {}).pop(entity_id, None)
        self._by_region[region_id][entity_id] = entity
        self._entity_region[entity_id] = region_id

    def remove(self, entity_id: str) -> bool:
        region_id = self._entity_region.pop(entity_id, None)
        if region_id is None:
            return False
        self._by_region.get(region_id, {}).pop(entity_id, None)
        return True

    def entities_for_regions(self, region_ids: Iterable[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for region_id in sorted(set(region_ids)):
            bucket = self._by_region.get(region_id, {})
            for entity_id in sorted(bucket):
                rows.append(bucket[entity_id])
        return rows

    def candidate_region_ids(
        self,
        *,
        catalog: RegionCatalog,
        current_region_id: str,
        include_neighbor_depth: int = 1,
    ) -> list[str]:
        if include_neighbor_depth < 0:
            raise ValueError("include_neighbor_depth must be >= 0")
        if catalog.get(current_region_id) is None:
            return []

        visited = {current_region_id}
        frontier = [current_region_id]
        for _ in range(include_neighbor_depth):
            next_frontier: list[str] = []
            for region_id in frontier:
                region = catalog.get(region_id)
                if region is None:
                    continue
                for neighbor in sorted(region.neighbors):
                    if neighbor in visited or catalog.get(neighbor) is None:
                        continue
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return sorted(visited)

    def candidates(
        self,
        *,
        catalog: RegionCatalog,
        current_region_id: str,
        include_neighbor_depth: int = 1,
    ) -> dict[str, Any]:
        region_ids = self.candidate_region_ids(
            catalog=catalog,
            current_region_id=current_region_id,
            include_neighbor_depth=include_neighbor_depth,
        )
        entities = self.entities_for_regions(region_ids)
        return {
            "region_ids": region_ids,
            "entities": entities,
            "candidates_examined": len(entities),
        }

    def size(self) -> int:
        return len(self._entity_region)
