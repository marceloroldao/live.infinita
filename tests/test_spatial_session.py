from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "world-runtime" / "spatial_session.py"
spec = importlib.util.spec_from_file_location("spatial_session", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["spatial_session"] = module
spec.loader.exec_module(module)
SpatialSession = module.SpatialSession


class SpatialSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = SpatialSession()
        self.world = {
            "world_id": "test",
            "version": 7,
            "sequence": 19,
            "environment": {"biome": "forest"},
            "entities": [
                {"id": "nov", "type": "human", "position": {"x": 100, "y": 100}, "properties": {"importance": 1.0}},
                {"id": "tree_near", "type": "tree", "position": {"x": 140, "y": 110}},
                {"id": "tree_warm", "type": "tree", "position": {"x": 370, "y": 100}},
                {"id": "castle_far", "type": "building", "position": {"x": 1100, "y": 650}},
            ],
            "regions": [
                {"id": "forest_a", "center": {"x": 100, "y": 100}, "radius": 150},
                {"id": "field_b", "center": {"x": 520, "y": 100}, "radius": 120},
            ],
        }

    def test_default_view_prefers_first_human(self) -> None:
        view = self.session.default_view(self.world)
        self.assertEqual(view["observer_entity_id"], "nov")
        self.assertEqual(view["position"], {"x": 100, "y": 100})

    def test_local_slice_materializes_only_hot_entities(self) -> None:
        local = self.session.build(self.world, self.session.default_view(self.world))
        ids = {row["id"] for row in local["entities"]}
        self.assertEqual(ids, {"nov", "tree_near"})
        self.assertTrue(local["interest"]["cold_omitted"])
        self.assertIn("tree_warm", local["interest"]["warm"]["entity_ids"])
        self.assertNotIn("castle_far", local["interest"]["warm"]["entity_ids"])

    def test_warm_entities_are_metadata_not_full_materialization(self) -> None:
        local = self.session.build(self.world, self.session.default_view(self.world))
        warm = {row["id"]: row for row in local["interest"]["warm_entities"]}
        self.assertEqual(set(warm), {"tree_warm"})
        self.assertNotIn("properties", warm["tree_warm"])

    def test_source_world_is_not_mutated(self) -> None:
        before = repr(self.world)
        self.session.build(self.world, self.session.default_view(self.world))
        self.assertEqual(repr(self.world), before)

    def test_world_message_protocol_remains_backward_compatible(self) -> None:
        wrapped = self.session.wrap_world_message(
            {"type": "world_state", "world": self.world, "event": {"event_id": "e1"}},
            self.session.default_view(self.world),
        )
        self.assertEqual(wrapped["type"], "world_state")
        self.assertEqual(wrapped["delivery"]["mode"], "local_world_slice")
        self.assertEqual(wrapped["delivery"]["observer_entity_id"], "nov")
        self.assertEqual(wrapped["event"]["event_id"], "e1")

    def test_interest_update_normalizes_position_direction_and_observer(self) -> None:
        fallback = self.session.default_view(self.world)
        view = self.session.normalize_view(
            {
                "observer_entity_id": "",
                "position": {"x": 250, "y": 260},
                "direction": {"x": 0, "y": -1},
            },
            fallback,
        )
        self.assertIsNone(view["observer_entity_id"])
        self.assertEqual(view["position"], {"x": 250.0, "y": 260.0})
        self.assertEqual(view["direction"], {"x": 0.0, "y": -1.0})

    def test_observer_entity_follows_authoritative_world_position(self) -> None:
        view = self.session.default_view(self.world)
        self.world["entities"][0]["position"] = {"x": 500, "y": 420}
        resolved = self.session.resolve_observer(self.world, view)
        self.assertEqual(resolved, {"x": 500.0, "y": 420.0})
        wrapped = self.session.wrap_world_message({"type": "world_state", "world": self.world}, view)
        self.assertEqual(wrapped["delivery"]["observer"], {"x": 500.0, "y": 420.0})


if __name__ == "__main__":
    unittest.main()
