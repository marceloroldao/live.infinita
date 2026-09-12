from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))
MODULE = RUNTIME / "cold_engine.py"
spec = importlib.util.spec_from_file_location("cold_engine_test_module", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["cold_engine_test_module"] = module
spec.loader.exec_module(module)
ColdAuthoritativeWorldEngine = module.ColdAuthoritativeWorldEngine

from packages.spatial import FileRegionColdStore


class ColdAuthoritativeWorldEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bootstrap = root / "bootstrap.json"
        self.data_dir = root / "data"
        self.store = FileRegionColdStore(root / "cold")
        self.bootstrap.write_text(json.dumps({
            "world_id": "cold-test",
            "version": 1,
            "sequence": 0,
            "regions": [
                {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 200, "neighbors": ["r1"]},
                {"id": "r1", "center": {"x": 400, "y": 0}, "radius": 200, "neighbors": ["r0"]},
            ],
            "environment": {"period": "day", "biome": "forest"},
            "entities": [
                {"id": "tree_01", "type": "tree", "region_id": "r0", "position": {"x": 20, "y": 0}, "properties": {}},
                {"id": "fire_01", "type": "campfire", "region_id": "r0", "position": {"x": 80, "y": 0}, "properties": {"lit": True}},
                {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}, "properties": {"role": "observer"}},
            ],
            "narration": {"text": ""},
        }), encoding="utf-8")
        self.engine = ColdAuthoritativeWorldEngine(self.bootstrap, self.data_dir, self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bootstrap_externalizes_all_entities(self) -> None:
        world = self.engine.load_world()
        self.assertEqual(world["entities"], [])
        self.assertEqual(world["cold_entities"]["entities_total"], 3)
        self.assertEqual(self.store.entities_total(), 3)
        self.assertIsNotNone(self.store.get_entity("nov"))

    def test_entity_actions_mutate_cold_store_not_world_entity_list(self) -> None:
        _, delta1, world1 = self.engine.commit_action("move_tree")
        self.assertEqual(world1["entities"], [])
        self.assertEqual(self.store.get_entity("tree_01")["position"]["x"], 360)
        self.assertEqual(delta1["operations"][0]["path"], ["entities", "tree_01", "position", "x"])

        _, _, world2 = self.engine.commit_action("toggle_fire")
        self.assertFalse(self.store.get_entity("fire_01")["properties"]["lit"])
        self.assertEqual(world2["entities"], [])

    def test_non_entity_action_stays_in_resident_world(self) -> None:
        _, _, world = self.engine.commit_action("set_night")
        self.assertEqual(world["environment"]["period"], "night")
        self.assertEqual(world["entities"], [])

    def test_spawn_writes_directly_to_cold_region(self) -> None:
        self.engine.commit_action("spawn_person")
        person = self.store.get_entity("person_01")
        self.assertIsNotNone(person)
        self.assertEqual(person["region_id"], "r0")
        self.assertEqual(self.engine.load_world()["entities"], [])

    def test_delta_hash_chain_replays_without_rehydrating_entities(self) -> None:
        self.engine.commit_action("move_tree")
        self.engine.commit_action("toggle_fire")
        self.engine.commit_action("set_night")
        verification = self.engine.verify_replay()
        self.assertTrue(verification["ok"])
        self.assertEqual(verification["events"], 3)
        self.assertEqual(verification["deltas"], 3)

    def test_restart_preserves_authoritative_cold_state_and_replay(self) -> None:
        self.engine.commit_action("move_tree")
        state_hash = self.engine.load_world()["state_hash"]
        reopened_store = FileRegionColdStore(self.store.root)
        reopened = ColdAuthoritativeWorldEngine(self.bootstrap, self.data_dir, reopened_store)
        self.assertEqual(reopened.load_world()["state_hash"], state_hash)
        self.assertEqual(reopened_store.get_entity("tree_01")["position"]["x"], 360)
        self.assertTrue(reopened.verify_replay()["ok"])


if __name__ == "__main__":
    unittest.main()
