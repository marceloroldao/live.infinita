from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "world-runtime" / "spatial_session.py"
spec = importlib.util.spec_from_file_location("spatial_session_indexed", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["spatial_session_indexed"] = module
spec.loader.exec_module(module)
SpatialSession = module.SpatialSession


def make_world(region_count: int = 512, entities_per_region: int = 80) -> dict:
    spacing = 500.0
    regions = []
    entities = []
    for i in range(region_count):
        region_id = f"r{i:04d}"
        neighbors = []
        if i > 0:
            neighbors.append(f"r{i-1:04d}")
        if i + 1 < region_count:
            neighbors.append(f"r{i+1:04d}")
        center_x = i * spacing
        regions.append(
            {
                "id": region_id,
                "center": {"x": center_x, "y": 0.0},
                "radius": 240.0,
                "biome": "forest" if i % 2 == 0 else "field",
                "neighbors": neighbors,
            }
        )
        for j in range(entities_per_region):
            entity_id = "nov" if i == 256 and j == 0 else f"e{i:04d}_{j:03d}"
            entities.append(
                {
                    "id": entity_id,
                    "type": "human" if entity_id == "nov" else "tree",
                    "region_id": region_id,
                    "position": {"x": center_x + (j % 10) * 8.0, "y": (j // 10) * 8.0},
                    "properties": {"importance": 1.0 if entity_id == "nov" else 0.0},
                }
            )
    return {
        "world_id": "indexed-scale",
        "version": 1,
        "sequence": 1,
        "environment": {"biome": "forest"},
        "regions": regions,
        "entities": entities,
    }


class IndexedSpatialSessionScaleTest(unittest.TestCase):
    def test_runtime_slice_uses_only_current_and_neighbor_region_candidates(self):
        world = make_world()
        session = SpatialSession()
        view = session.default_view(world)
        local = session.build(world, view)

        self.assertEqual(local["interest"]["mode"], "region_entity_index")
        self.assertEqual(local["interest"]["current_region_id"], "r0256")
        self.assertEqual(local["interest"]["candidates_examined"], 240)
        self.assertEqual(local["interest"]["indexed_entities_total"], 40960)
        self.assertLessEqual(len(local["interest"]["hot"]["entity_ids"]), 96)
        self.assertLessEqual(len(local["interest"]["warm"]["entity_ids"]), 192)
        self.assertTrue(local["interest"]["cold_omitted"])

    def test_candidate_cost_does_not_grow_with_total_world_size(self):
        examined = []
        for count in (8, 64, 512):
            world = make_world(region_count=count)
            # Put the observer in a middle region for every universe size.
            middle = count // 2
            nov = next(row for row in world["entities"] if row["region_id"] == f"r{middle:04d}")
            nov["id"] = "nov"
            nov["type"] = "human"
            session = SpatialSession()
            local = session.build(world, session.default_view(world))
            examined.append(local["interest"]["candidates_examined"])
        self.assertEqual(examined, [240, 240, 240])

    def test_delta_updates_observer_region_incrementally(self):
        world = make_world(region_count=32)
        # Re-home Nov into r0010 for this smaller world.
        original = next(row for row in world["entities"] if row["id"] == "nov") if any(row["id"] == "nov" for row in world["entities"]) else None
        if original is None:
            original = world["entities"][10 * 80]
            original["id"] = "nov"
            original["type"] = "human"
        original["region_id"] = "r0010"
        original["position"] = {"x": 5000.0, "y": 0.0}

        session = SpatialSession()
        view = session.default_view(world)
        first = session.wrap_world_message({"type": "world_state", "world": world}, view)
        self.assertEqual(first["delivery"]["candidate_mode"], "region_entity_index")

        moved = copy.deepcopy(world)
        moved["sequence"] = 2
        moved["version"] = 2
        nov = next(row for row in moved["entities"] if row["id"] == "nov")
        nov["region_id"] = "r0011"
        nov["position"] = {"x": 5500.0, "y": 0.0}
        delta = {
            "operations": [
                {"op": "set", "path": ["entities", "nov", "region_id"], "value": "r0011"},
                {"op": "set", "path": ["entities", "nov", "position", "x"], "value": 5500.0},
            ]
        }
        second = session.wrap_world_message({"type": "world_state", "world": moved, "delta": delta}, view)
        self.assertEqual(second["world"]["interest"]["current_region_id"], "r0011")
        self.assertLessEqual(second["delivery"]["candidates_examined"], 240)
        self.assertEqual(second["delivery"]["observer"], {"x": 5500.0, "y": 0.0})

    def test_legacy_world_remains_supported(self):
        world = {
            "sequence": 1,
            "entities": [
                {"id": "nov", "type": "human", "position": {"x": 10, "y": 10}},
                {"id": "tree", "type": "tree", "position": {"x": 20, "y": 10}},
            ],
            "regions": [{"id": "legacy", "center": {"x": 0, "y": 0}, "radius": 100}],
        }
        session = SpatialSession()
        local = session.build(world, session.default_view(world))
        self.assertEqual(local["interest"]["mode"], "legacy_global_scan")
        self.assertEqual(local["interest"]["candidates_examined"], 2)


if __name__ == "__main__":
    unittest.main()
