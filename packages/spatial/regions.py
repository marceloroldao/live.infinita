from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Region:
    id: str
    center: tuple[float, float]
    radius: float
    biome: str = "unknown"
    neighbors: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_resolver_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "center": {"x": self.center[0], "y": self.center[1]},
            "radius": self.radius,
            "biome": self.biome,
            "neighbors": list(self.neighbors),
            "metadata": dict(self.metadata),
        }


class RegionCatalog:
    """Deterministic persistent world-region metadata catalog."""

    def __init__(self, regions: list[Region] | None = None) -> None:
        self._regions: dict[str, Region] = {}
        for region in regions or []:
            self.add(region)

    def add(self, region: Region) -> None:
        if not region.id.strip():
            raise ValueError("region id is required")
        if region.radius <= 0:
            raise ValueError("region radius must be positive")
        self._regions[region.id] = region

    def get(self, region_id: str) -> Region | None:
        return self._regions.get(region_id)

    def size(self) -> int:
        return len(self._regions)

    def all(self) -> list[Region]:
        return [self._regions[key] for key in sorted(self._regions)]

    def resolver_rows(self) -> list[dict[str, Any]]:
        return [region.as_resolver_dict() for region in self.all()]

    def route(self, start_id: str, end_id: str) -> list[str]:
        if start_id == end_id:
            return [start_id] if start_id in self._regions else []
        if start_id not in self._regions or end_id not in self._regions:
            return []

        queue: list[str] = [start_id]
        previous: dict[str, str | None] = {start_id: None}
        while queue:
            current = queue.pop(0)
            for neighbor in sorted(self._regions[current].neighbors):
                if neighbor not in self._regions or neighbor in previous:
                    continue
                previous[neighbor] = current
                if neighbor == end_id:
                    queue.clear()
                    break
                queue.append(neighbor)

        if end_id not in previous:
            return []
        path: list[str] = []
        cursor: str | None = end_id
        while cursor is not None:
            path.append(cursor)
            cursor = previous[cursor]
        path.reverse()
        return path
