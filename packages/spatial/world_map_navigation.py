"""Read-only spatial navigation contract for the Vale de Nov visual map.

Not wired to the live world engine: explicit coordinate-frame and region-id
checks prevent the old 2D World State from being silently reinterpreted.
"""
from __future__ import annotations

from collections import deque
from math import floor, isfinite
from typing import Any, Mapping

MAP_SCHEMA = "live-infinita-visual-world-map/v1"
MAP_FRAME = "vale-nov/v1"
BRIDGE_CELL = (8, 7)


class WorldMapNavigation:
    def __init__(self, manifest: Mapping[str, Any]) -> None:
        if manifest.get("schema") != MAP_SCHEMA:
            raise ValueError("unsupported visual map manifest")
        if manifest.get("grid_size") != 16 or manifest.get("tile_size_m") != 64:
            raise ValueError("unexpected Vale de Nov grid geometry")
        if manifest.get("active_radius_tiles") != 1:
            raise ValueError("unexpected active sector radius")
        self.grid_size = 16
        self.tile_size = 64.0
        self.half_extent = self.grid_size * self.tile_size / 2.0
        landmarks = manifest.get("landmarks")
        if not isinstance(landmarks, list):
            raise ValueError("landmark list missing")
        self.landmarks: dict[str, tuple[int, int]] = {}
        for row in landmarks:
            if not isinstance(row, dict):
                raise ValueError("invalid landmark")
            name = row.get("id")
            cell = row.get("cell")
            if not isinstance(name, str) or not name or name in self.landmarks:
                raise ValueError("invalid or duplicate landmark id")
            coords = self._read_cell(cell)
            if coords is None:
                raise ValueError("landmark outside map")
            self.landmarks[name] = coords
        if self.landmarks.get("river_crossing") != BRIDGE_CELL:
            raise ValueError("river crossing does not match bridge tile")
        route = manifest.get("route")
        if not isinstance(route, list) or len(route) < 2:
            raise ValueError("visual route missing")
        self.route = tuple(self._require_cell(cell) for cell in route)
        if self.route[0] != self.route[-1]:
            raise ValueError("visual route is not a closed tour")
        if not all(cell in self.route for cell in self.landmarks.values()):
            raise ValueError("a landmark is missing from the visual tour")

    def _read_cell(self, value: Any) -> tuple[int, int] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        x, z = value
        if type(x) is not int or type(z) is not int:
            return None
        return (x, z) if 0 <= x < self.grid_size and 0 <= z < self.grid_size else None

    def _require_cell(self, value: Any) -> tuple[int, int]:
        cell = self._read_cell(value)
        if cell is None:
            raise ValueError("route cell outside map")
        return cell

    def cell_id(self, cell: tuple[int, int]) -> str:
        x, z = self._require_cell(cell)
        return f"{MAP_FRAME}/{x:02d}/{z:02d}"

    def coordinates(self, cell: tuple[int, int]) -> tuple[float, float]:
        x, z = self._require_cell(cell)
        return (
            (x + 0.5) * self.tile_size - self.half_extent,
            (z + 0.5) * self.tile_size - self.half_extent,
        )

    def position_cell(self, x: Any, z: Any) -> tuple[int, int] | None:
        if type(x) not in (int, float) or type(z) not in (int, float):
            return None
        if not (isfinite(x) and isfinite(z)):
            return None
        if not (-self.half_extent <= x < self.half_extent):
            return None
        if not (-self.half_extent <= z < self.half_extent):
            return None
        return (floor((x + self.half_extent) / self.tile_size),
                floor((z + self.half_extent) / self.tile_size))

    def biome(self, cell: tuple[int, int]) -> str:
        x, z = self._require_cell(cell)
        if x == 8:
            return "river"
        if abs(x - 11) <= 1 and abs(z - 9) <= 1:
            return "village"
        if x >= 11 and z <= 5:
            return "hills"
        if abs(x - 5) <= 1 and abs(z - 7) <= 1:
            return "clearing"
        return "forest"

    def accessible(self, cell: tuple[int, int]) -> bool:
        return self._read_cell(cell) is not None and (
            self.biome(cell) != "river" or cell == BRIDGE_CELL
        )

    def active_cells(self, x: Any, z: Any) -> tuple[tuple[int, int], ...]:
        center = self.position_cell(x, z)
        if center is None:
            return ()
        cx, cz = center
        cells = [
            (xx, zz)
            for zz in range(max(0, cz - 1), min(self.grid_size, cz + 2))
            for xx in range(max(0, cx - 1), min(self.grid_size, cx + 2))
        ]
        return tuple(cells)

    def path(self, start: tuple[int, int], target: tuple[int, int]) -> tuple[tuple[int, int], ...]:
        if not self.accessible(start) or not self.accessible(target):
            return ()
        queue = deque([start])
        previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        while queue:
            cell = queue.popleft()
            if cell == target:
                break
            x, z = cell
            for nxt in ((x, z - 1), (x + 1, z), (x, z + 1), (x - 1, z)):
                if nxt in previous or not self.accessible(nxt):
                    continue
                previous[nxt] = cell
                queue.append(nxt)
        if target not in previous:
            return ()
        result = []
        current: tuple[int, int] | None = target
        while current is not None:
            result.append(current)
            current = previous[current]
        result.reverse()
        return tuple(result)

    def path_to_landmark(self, start: tuple[int, int], landmark_id: str) -> tuple[tuple[int, int], ...]:
        target = self.landmarks.get(landmark_id)
        return self.path(start, target) if target is not None else ()

    def project_nov(self, world: Mapping[str, Any]) -> dict[str, Any]:
        """Return a local view only for an explicitly bound authoritative Nov.

        Uses World State x/y as visual x/z only with an explicit frame marker.
        No mutation, inferred frame, new entity, or stored navigation intent.
        """
        entities = world.get("entities")
        if not isinstance(entities, list):
            return {"status": "unbound", "reason": "no_entities"}
        nov = next((e for e in entities if isinstance(e, dict) and e.get("id") == "nov"), None)
        if nov is None:
            return {"status": "unbound", "reason": "nov_not_materialized"}
        if nov.get("position_frame") != MAP_FRAME:
            return {"status": "unbound", "reason": "coordinate_frame_not_bound"}
        position = nov.get("position")
        if not isinstance(position, dict):
            return {"status": "unbound", "reason": "position_missing"}
        cell = self.position_cell(position.get("x"), position.get("y"))
        if cell is None:
            return {"status": "unbound", "reason": "position_outside_map"}
        region_id = self.cell_id(cell)
        if nov.get("region_id") != region_id:
            return {"status": "unbound", "reason": "region_position_mismatch"}
        active = self.active_cells(position["x"], position["y"])
        return {
            "status": "read_only",
            "map_frame": MAP_FRAME,
            "region_id": region_id,
            "cell": list(cell),
            "active_region_ids": [self.cell_id(item) for item in active],
            "active_count": len(active),
            "world_mutated": False,
            "selection_authority": False,
        }
