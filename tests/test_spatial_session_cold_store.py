from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from packages.spatial import FileRegionColdStore, externalize_world_entities

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "world-runtime" / "spatial_session.py"
spec = importlib.util.spec_from_file_location("spatial_session_cold_store", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["spatial_session_cold_store"] = module
spec.loader.exec_module(module)
SpatialSession = module.SpatialSession


class SpatialSessionColdStoreTest(unittest.TestCase):
    def _world(self) -> dict:
        return {
            "world_id": "cold-world",
            "version": 1,
            "sequence": 1,
            "environment": {"biome": "forest"},
            "regions": [
                {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 180, "neighbors": ["r1"], "biome": "forest"},
                {"id": "r1", "center": {"x": 300, "y": 0}, "radius": 180, "neighbors": ["r0", "r2"], "biome": "field"},
                {"id": "r2", "center": {"x": 600, "y": 0}, "radius": 180, "neighbors": ["r1"], "biome": "village"},
            ],
            "entities": [
                {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}, "properties": {"role": "observer"}},
                {"id": "tree", "type": "tree", "region_id": "r0", "position": {"x": 60, "y": 0}},
                {"id": "bridge", "type": "bridge", "region_id": "r1", "position": {"x": 280, "y": 0}},
                {"id": "house", "type": "building", "region_id": "r2", "position": {"x": 610, "y": 0}},
            ],
        }

    def test_entity_empty_world_resolves_hot_warm_from_cold_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp))
            world = externalize_world_entities(self._world(), store)
            world["cold_entities"]["default_observer_entity_id"] = "nov"
            self.assertEqual(world["entities"], [])
            self.assertEqual(store.stats()["payload_resident_entities"], 0)

            session = SpatialSession(cold_store=store)
            view = session.default_view(world)
            local = session.build(world, view)
            interest = local["interest"]

            self.assertEqual(view["observer_entity_id"], "nov")
            self.assertEqual(interest["mode"], "cold_region_store")
            self.assertEqual(interest["current_region_id"], "r0")
            self.assertEqual(interest["source_entities_total"], 4)
            self.assertLess(interest["candidates_examined"], interest["source_entities_total"] + 1)
            self.assertLessEqual(interest["cold_payload_resident_entities"], 3)
            self.assertIn("nov", {row["id"] for row in local["entities"]})
            self.assertTrue(interest["cold_omitted"])

    def test_cold_delta_moves_observer_without_rehydrating_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp))
            world = externalize_world_entities(self._world(), store)
            world["cold_entities"]["default_observer_entity_id"] = "nov"
            session = SpatialSession(cold_store=store)
            view = session.default_view(world)
            session.build(world, view)

            moved_world = dict(world)
            moved_world["sequence"] = 2
            moved_world["version"] = 2
            delta = {
                "operations": [
                    {"op": "set", "path": ["entities", "nov", "region_id"], "value": "r1"},
                    {"op": "set", "path": ["entities", "nov", "position", "x"], "value": 300},
                ]
            }
            local = session.build(moved_world, view, delta=delta)

            self.assertEqual(moved_world["entities"], [])
            self.assertEqual(store.entity_region("nov"), "r1")
            self.assertEqual(store.get_entity("nov")["position"]["x"], 300)
            self.assertEqual(local["interest"]["current_region_id"], "r1")
            self.assertEqual(local["interest"]["region_lookup_mode"], "cold_entity_region_manifest")


if __name__ == "__main__":
    unittest.main()
