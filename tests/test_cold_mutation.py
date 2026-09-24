from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from packages.spatial import ColdEntityMutator, ColdMutationError, FileRegionColdStore

ROOT = Path(__file__).resolve().parents[1]
ENGINE_MODULE = ROOT / "apps" / "world-runtime" / "cold_engine.py"
spec = importlib.util.spec_from_file_location("cold_engine_generic", ENGINE_MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["cold_engine_generic"] = module
spec.loader.exec_module(module)
ColdAuthoritativeWorldEngine = module.ColdAuthoritativeWorldEngine


class ColdMutationTest(unittest.TestCase):
    def test_generic_create_set_move_link_unlink_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp) / "cold")
            store.replace_all([
                {"id": "a", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}},
                {"id": "b", "type": "tree", "region_id": "r1", "position": {"x": 10, "y": 0}},
            ])
            mutator = ColdEntityMutator(store)

            mutator.apply({"op": "create", "entity": {"id": "c", "type": "marker", "region_id": "r0", "position": {"x": 2, "y": 3}}})
            mutator.apply({"op": "set", "entity_id": "c", "path": ["properties", "label"], "value": "C"})
            mutator.apply({"op": "move", "entity_id": "c", "position": {"x": 20, "y": 5}, "region_id": "r1"})
            mutator.apply({"op": "link", "entity_id": "a", "relation": "knows", "target_id": "c"})
            mutator.apply({"op": "link", "entity_id": "a", "relation": "knows", "target_id": "c"})

            c = store.get_entity("c")
            self.assertEqual(c["region_id"], "r1")
            self.assertEqual(c["position"], {"x": 20.0, "y": 5.0})
            self.assertEqual(c["properties"]["label"], "C")
            self.assertEqual(store.get_entity("a")["relations"]["knows"], ["c"])

            mutator.apply({"op": "unlink", "entity_id": "a", "relation": "knows", "target_id": "c"})
            self.assertEqual(store.get_entity("a")["relations"]["knows"], [])
            mutator.apply({"op": "remove", "entity_id": "c"})
            self.assertIsNone(store.get_entity("c"))

    def test_invalid_mutations_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp) / "cold")
            store.replace_all([{"id": "a", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}}])
            mutator = ColdEntityMutator(store)
            with self.assertRaises(ColdMutationError):
                mutator.apply({"op": "set", "entity_id": "missing", "path": ["x"], "value": 1})
            with self.assertRaises(ColdMutationError):
                mutator.apply({"op": "set", "entity_id": "a", "path": ["id"], "value": "other"})
            with self.assertRaises(ColdMutationError):
                mutator.apply({"op": "link", "entity_id": "a", "relation": "knows", "target_id": "missing"})

    def test_engine_commits_generic_operations_and_replay_hash_stays_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bootstrap = root / "bootstrap.json"
            bootstrap.write_text(json.dumps({
                "world_id": "generic-cold",
                "version": 1,
                "regions": [
                    {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 100, "neighbors": ["r1"], "biome": "field"},
                    {"id": "r1", "center": {"x": 200, "y": 0}, "radius": 100, "neighbors": ["r0"], "biome": "field"},
                ],
                "entities": [
                    {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}},
                    {"id": "tree", "type": "tree", "region_id": "r1", "position": {"x": 200, "y": 0}},
                ],
                "environment": {"period": "day", "biome": "field"},
                "narration": {"text": ""},
            }), encoding="utf-8")
            data_dir = root / "data"
            store = FileRegionColdStore(root / "cold")
            engine = ColdAuthoritativeWorldEngine(bootstrap, data_dir, store)

            event, delta, world = engine.commit_operations([
                {"op": "move", "entity_id": "nov", "position": {"x": 210, "y": 4}, "region_id": "r1"},
                {"op": "link", "entity_id": "nov", "relation": "sees", "target_id": "tree"},
                {"op": "set_world", "path": ["environment", "period"], "value": "night"},
            ], source="test", narration="Nov atravessa a fronteira.")

            self.assertEqual(event["type"], "generic_mutation")
            self.assertEqual(delta["operations"][0]["op"], "move")
            self.assertEqual(world["entities"], [])
            self.assertEqual(world["environment"]["period"], "night")
            self.assertEqual(store.entity_region("nov"), "r1")
            self.assertEqual(store.get_entity("nov")["relations"]["sees"], ["tree"])
            self.assertTrue(engine.verify_replay()["ok"])


if __name__ == "__main__":
    unittest.main()
