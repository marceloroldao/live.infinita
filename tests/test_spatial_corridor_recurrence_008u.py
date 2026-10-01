from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "cognitive_terrain_projection.py"
spec = importlib.util.spec_from_file_location("cognitive_terrain_projection_008u", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SpatialCorridorRecurrence008UTests(unittest.TestCase):
    def test_nearby_exact_segments_reinforce_same_64m_corridor(self) -> None:
        spatial = [
            {
                "sequence": 100,
                "trail": (101, 102),
                "from_position": {"x": 640.0, "y": 360.0},
                "to_position": {"x": 705.0, "y": 365.0},
                "from_region_id": "a",
                "to_region_id": "b",
            },
            {
                "sequence": 110,
                "trail": (901, 902),
                "from_position": {"x": 646.0, "y": 355.0},
                "to_position": {"x": 699.0, "y": 372.0},
                "from_region_id": "a",
                "to_region_id": "b",
            },
        ]
        projection = module.build_projection(
            world_id="world-test",
            known_regions=[
                {"region_id": "a", "center": {"x": 640.0, "y": 360.0}, "biome": "forest"},
                {"region_id": "b", "center": {"x": 704.0, "y": 360.0}, "biome": "hills"},
            ],
            records=[],
            source_snapshot_records=0,
            checkpoint_cursor=0,
            spatial_records=spatial,
        )
        self.assertEqual(projection["policy"]["spatial_recurrence_grid_m"], 64.0)
        self.assertEqual(len(projection["spatial_trails"]), 1)
        trail = projection["spatial_trails"][0]
        self.assertEqual(trail["count"], 2)
        self.assertTrue(trail["trail_candidate"])

    def test_sync_is_limited_to_one_structural_trajectory_per_run(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "nov_spatial_memory_sync.py").read_text(encoding="utf-8")
        unit = (ROOT / "deploy" / "live-infinita-nov-spatial-memory-sync.service").read_text(encoding="utf-8")
        self.assertIn("MAX_EVENTS_PER_RUN = 1", source)
        self.assertIn("--max-events 1", unit)


if __name__ == "__main__":
    unittest.main()
