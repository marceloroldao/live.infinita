from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import floor, hypot
from typing import Iterable

from .regions import Region, RegionCatalog


@dataclass(frozen=True)
class RegionLookupResult:
    region_id: str | None
    candidates_examined: int
    cell: tuple[int, int]


class RegionSpatialGrid:
    """Uniform-grid accelerator for deterministic position -> region lookup.

    Regions are inserted into every cell touched by their circular bounds. A
    lookup examines only the point cell and validates exact circle containment.
    If regions overlap, the nearest center wins; ties are broken by region id.
    """

    def __init__(self, regions: Iterable[Region] | None = None, *, cell_size: float = 512.0) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = float(cell_size)
        self._cells: dict[tuple[int, int], set[str]] = defaultdict(set)
        self._regions: dict[str, Region] = {}
        for region in regions or []:
            self.upsert(region)

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return floor(x / self.cell_size), floor(y / self.cell_size)

    def _covered_cells(self, region: Region) -> list[tuple[int, int]]:
        min_cell = self._cell(region.center[0] - region.radius, region.center[1] - region.radius)
        max_cell = self._cell(region.center[0] + region.radius, region.center[1] + region.radius)
        cells: list[tuple[int, int]] = []
        for cx in range(min_cell[0], max_cell[0] + 1):
            for cy in range(min_cell[1], max_cell[1] + 1):
                cells.append((cx, cy))
        return cells

    def upsert(self, region: Region) -> None:
        if region.radius <= 0:
            raise ValueError("region radius must be positive")
        previous = self._regions.get(region.id)
        if previous is not None:
            for cell in self._covered_cells(previous):
                bucket = self._cells.get(cell)
                if bucket is not None:
                    bucket.discard(region.id)
                    if not bucket:
                        self._cells.pop(cell, None)
        self._regions[region.id] = region
        for cell in self._covered_cells(region):
            self._cells[cell].add(region.id)

    def rebuild(self, catalog: RegionCatalog) -> None:
        self._cells.clear()
        self._regions.clear()
        for region in catalog.all():
            self.upsert(region)

    def lookup(self, x: float, y: float) -> RegionLookupResult:
        cell = self._cell(float(x), float(y))
        ids = sorted(self._cells.get(cell, set()))
        matches: list[tuple[float, str]] = []
        for region_id in ids:
            region = self._regions[region_id]
            distance = hypot(float(x) - region.center[0], float(y) - region.center[1])
            if distance <= region.radius:
                matches.append((distance, region_id))
        matches.sort(key=lambda item: (item[0], item[1]))
        return RegionLookupResult(
            region_id=matches[0][1] if matches else None,
            candidates_examined=len(ids),
            cell=cell,
        )

    def region_count(self) -> int:
        return len(self._regions)
