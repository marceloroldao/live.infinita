from __future__ import annotations

import unittest

from packages.spatial import Region, RegionCatalog, RegionSpatialGrid


def make_grid(side: int, spacing: float = 300.0, radius: float = 140.0) -> RegionCatalog:
    regions: list[Region] = []
    for y in range(side):
        for x in range(side):
            region_id = f"r_{x:04d}_{y:04d}"
            regions.append(Region(region_id, (x * spacing, y * spacing), radius))
    return RegionCatalog(regions)


class RegionSpatialGridTest(unittest.TestCase):
    def test_exact_lookup_returns_containing_region(self) -> None:
        catalog = make_grid(8)
        grid = RegionSpatialGrid(catalog.all(), cell_size=256.0)
        result = grid.lookup(3 * 300.0 + 20.0, 5 * 300.0 - 10.0)
        self.assertEqual(result.region_id, "r_0003_0005")
        self.assertLessEqual(result.candidates_examined, 4)

    def test_lookup_cost_does_not_follow_total_region_count(self) -> None:
        examined: list[int] = []
        totals: list[int] = []
        for side in (8, 32, 128):
            catalog = make_grid(side)
            grid = RegionSpatialGrid(catalog.all(), cell_size=256.0)
            x = (side // 2) * 300.0
            y = (side // 2) * 300.0
            result = grid.lookup(x, y)
            self.assertIsNotNone(result.region_id)
            examined.append(result.candidates_examined)
            totals.append(catalog.size())
        self.assertEqual(totals, [64, 1024, 16384])
        self.assertLessEqual(max(examined), 4)

    def test_overlap_is_deterministic_nearest_then_id(self) -> None:
        catalog = RegionCatalog([
            Region("b", (0.0, 0.0), 200.0),
            Region("a", (0.0, 0.0), 200.0),
            Region("near", (20.0, 0.0), 200.0),
        ])
        grid = RegionSpatialGrid(catalog.all(), cell_size=256.0)
        self.assertEqual(grid.lookup(0.0, 0.0).region_id, "a")
        self.assertEqual(grid.lookup(19.0, 0.0).region_id, "near")


if __name__ == "__main__":
    unittest.main()
