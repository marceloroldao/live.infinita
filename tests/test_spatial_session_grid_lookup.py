from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "world-runtime" / "spatial_session.py"
spec = importlib.util.spec_from_file_location("spatial_session_grid_lookup", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["spatial_session_grid_lookup"] = module
spec.loader.exec_module(module)
SpatialSession = module.SpatialSession


class SpatialSessionGridLookupTest(unittest.TestCase):
    def test_anonymous_position_uses_grid_not_region_scan(self) -> None:
        side = 32
        spacing = 300.0
        regions = []
        entities = []
        for y in range(side):
            for x in range(side):
                rid = f"r_{x:03d}_{y:03d}"
                neighbors = []
                if x > 0: neighbors.append(f"r_{x-1:03d}_{y:03d}")
                if x + 1 < side: neighbors.append(f"r_{x+1:03d}_{y:03d}")
                if y > 0: neighbors.append(f"r_{x:03d}_{y-1:03d}")
                if y + 1 < side: neighbors.append(f"r_{x:03d}_{y+1:03d}")
                regions.append({
                    "id": rid,
                    "center": {"x": x * spacing, "y": y * spacing},
                    "radius": 140.0,
                    "neighbors": neighbors,
                    "biome": "field",
                })
                entities.append({
                    "id": f"e_{x:03d}_{y:03d}",
                    "type": "marker",
                    "region_id": rid,
                    "position": {"x": x * spacing, "y": y * spacing},
                })
        world = {
            "world_id": "grid-scale",
            "version": 1,
            "sequence": 1,
            "regions": regions,
            "entities": entities,
            "environment": {"biome": "field"},
        }
        target_x = 17
        target_y = 19
        view = {
            "observer_entity_id": None,
            "position": {"x": target_x * spacing, "y": target_y * spacing},
            "direction": {"x": 1.0, "y": 0.0},
            "mode": "local",
        }
        local = SpatialSession().build(world, view)
        interest = local["interest"]
        self.assertEqual(interest["region_lookup_mode"], "region_spatial_grid")
        self.assertEqual(interest["current_region_id"], f"r_{target_x:03d}_{target_y:03d}")
        # Region circles may overlap adjacent grid cells, so a local lookup can
        # legitimately inspect six candidates in this geometry. The invariant
        # is locality: six candidates out of 1,024 regions, not a global scan.
        self.assertLessEqual(interest["region_candidates_examined"], 6)
        self.assertLess(interest["region_candidates_examined"], (side * side) // 100)
        self.assertLessEqual(interest["candidates_examined"], 5)
        self.assertEqual(interest["source_regions_total"], side * side)
        self.assertEqual(interest["source_entities_total"], side * side)


if __name__ == "__main__":
    unittest.main()
