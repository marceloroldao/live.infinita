from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "world-runtime" / "spatial_session.py"
spec = importlib.util.spec_from_file_location("spatial_multi_observer", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["spatial_multi_observer"] = module
spec.loader.exec_module(module)
SpatialSession = module.SpatialSession


class SpatialMultiObserverTest(unittest.TestCase):
    def test_shared_index_produces_independent_local_slices(self):
        world = {
            "sequence": 1,
            "version": 1,
            "regions": [
                {"id": "west", "center": {"x": 0, "y": 0}, "radius": 250, "neighbors": ["middle"]},
                {"id": "middle", "center": {"x": 500, "y": 0}, "radius": 250, "neighbors": ["west", "east"]},
                {"id": "east", "center": {"x": 1000, "y": 0}, "radius": 250, "neighbors": ["middle"]},
            ],
            "entities": [
                {"id": "nov", "type": "human", "region_id": "west", "position": {"x": 0, "y": 0}},
                {"id": "luna", "type": "human", "region_id": "east", "position": {"x": 1000, "y": 0}},
                {"id": "west_tree", "type": "tree", "region_id": "west", "position": {"x": 40, "y": 0}},
                {"id": "east_tree", "type": "tree", "region_id": "east", "position": {"x": 960, "y": 0}},
            ],
        }
        session = SpatialSession()
        nov_view = {"observer_entity_id": "nov", "position": {"x": 0, "y": 0}, "direction": {"x": 1, "y": 0}, "mode": "local"}
        luna_view = {"observer_entity_id": "luna", "position": {"x": 1000, "y": 0}, "direction": {"x": -1, "y": 0}, "mode": "local"}

        nov_slice = session.build(world, nov_view)
        luna_slice = session.build(world, luna_view)

        self.assertEqual(nov_slice["interest"]["current_region_id"], "west")
        self.assertEqual(luna_slice["interest"]["current_region_id"], "east")
        self.assertIn("west_tree", {row["id"] for row in nov_slice["entities"]})
        self.assertNotIn("east_tree", {row["id"] for row in nov_slice["entities"]})
        self.assertIn("east_tree", {row["id"] for row in luna_slice["entities"]})
        self.assertNotIn("west_tree", {row["id"] for row in luna_slice["entities"]})
        self.assertEqual(nov_slice["interest"]["indexed_entities_total"], 4)
        self.assertEqual(luna_slice["interest"]["indexed_entities_total"], 4)


if __name__ == "__main__":
    unittest.main()
