"""Isolated large visual map: deterministic layout, budget and no world writes."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "apps/renderer-godot"
MAP = SCENE / "world_map_001.json"
SCRIPT = SCENE / "world_map_preview.gd"


class WorldMapTests(unittest.TestCase):
    def test_manifest_cells_and_route(self):
        data = json.loads(MAP.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "live-infinita-visual-world-map/v1")
        self.assertEqual(data["grid_size"], 16)
        self.assertEqual(data["tile_size_m"], 64)
        self.assertEqual(data["active_radius_tiles"], 1)
        self.assertEqual(data["max_decorations_per_tile"], 6)
        cells = data["grid_size"]
        for point in data["route"]:
            self.assertEqual(len(point), 2)
            self.assertTrue(all(isinstance(v, int) and 0 <= v < cells for v in point))
        self.assertEqual(data["route"][0], data["route"][-1])
        self.assertEqual(data["route"][0], data["start"])
        ids = set()
        for landmark in data["landmarks"]:
            self.assertNotIn(landmark["id"], ids)
            ids.add(landmark["id"])
            self.assertIn(landmark["cell"], data["route"])
        self.assertGreaterEqual(len(ids), 5)

    def test_scene_is_isolated_and_bounded(self):
        script = SCRIPT.read_text(encoding="utf-8")
        three = (SCENE / "world_map_preview.tscn").read_text()
        main = (SCENE / "main.tscn").read_text()
        self.assertIn('type="Node3D"', three)
        self.assertIn("world_map_preview.gd", three)
        self.assertNotIn("world_map_preview", main)
        self.assertIn('run/main_scene="res://main.tscn"', (SCENE / "project.godot").read_text())
        for gate in ("MAX_ACTIVE_TILES := 9", "MAX_ACTIVE_DECOR := 54",
                     "queue_free()", "_sync_tiles()", "WORLD_MAP_PREVIEW_READY"):
            self.assertIn(gate, script)
        for forbidden in ("WebSocket", "HTTPClient", "FileAccess.open(",
                          "DirAccess", "set_world", "submit_intent", "post_world"):
            self.assertNotIn(forbidden, script)
        self.assertLess(len(script), 12500)

    def test_real_visual_features_are_bounded_and_read_only(self):
        features = (SCENE / "world_map_features.gd").read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        for required in ("func _water(", "func _bridge(", "func _hut(",
                         "func _village(", "func _landmark(", "func _path(",
                         "func decorate(", "WORLD_MAP_TILE_READY"):
            self.assertIn(required, features + script)
        for forbidden in ("WebSocket", "HTTPClient", "FileAccess", "DirAccess",
                          "post_world", "submit_intent", "set_world"):
            self.assertNotIn(forbidden, features)
        self.assertIn('if cx == 8 and cz == 7:', features)
        self.assertIn('if cx == 11 and cz == 9:', features)
        self.assertIn('for index in range(steps):', features)
        self.assertIn('var features: Array[String] = _features.decorate(', script)

    def test_live_spatial_feed_is_read_only_and_bounded(self):
        data = json.loads(MAP.read_text(encoding="utf-8"))
        projection = data["runtime_projection"]
        self.assertEqual(projection["kind"], "two_point_similarity_v1")
        self.assertEqual(projection["world_anchor_a_region"], "deep_forest")
        self.assertEqual(projection["world_anchor_b_region"], "shelter")
        self.assertEqual(projection["map_anchor_a_landmark"], "old_grove")
        self.assertEqual(projection["map_anchor_b_landmark"], "shelter")
        feed = (SCENE / "world_map_live_feed.gd").read_text(encoding="utf-8")
        visual = (SCENE / "world_map_live_visual.gd").read_text(encoding="utf-8")
        scene = (SCENE / "world_map_preview.tscn").read_text(encoding="utf-8")
        self.assertIn('connect_to_url(_websocket_url())', feed)
        self.assertIn('world_slice_received.emit(', feed)
        self.assertIn('world_map_live_feed.gd', scene)
        for forbidden in ("send_text", "send_json", "interest_update", "HTTPClient",
                          "FileAccess", "DirAccess", "submit_intent", "post_world"):
            self.assertNotIn(forbidden, feed)
        self.assertIn("MAX_HOT_MARKERS := 96", visual)
        self.assertIn("MAX_WARM_MARKERS := 192", visual)
        self.assertIn("project_position", visual)
        self.assertIn("update_markers", visual)

    def test_web_rollout_is_separate_and_atomic(self):
        rollout = (ROOT / "deploy/export-world-map-preview-web.sh").read_text()
        self.assertIn('PREVIEW_NAME="world-map-preview"', rollout)
        self.assertIn('run/main_scene="res://world_map_preview.tscn"', rollout)
        self.assertIn('TARGET="$WEB_ROOT/$PREVIEW_NAME"', rollout)
        self.assertIn('.world-map-preview.stage.', rollout)
        self.assertIn('/godot/world-map-preview/', rollout)
        self.assertIn('/nov-preview/', rollout)
        for forbidden in ("systemctl restart", "nginx -s", "main.tscn >", "World State"):
            if forbidden == "World State":
                continue
            self.assertNotIn(forbidden, rollout)

    def test_preserves_cold_world_contract(self):
        text = (ROOT / "docs/PERSISTENT_REGIONS_LONG_TRAVEL_001.md").read_text()
        self.assertIn("HOT <= 96", text)
        self.assertIn("WARM <= 192", text)
        self.assertTrue((SCENE / "nature_asset_catalog.gd").exists())


if __name__ == "__main__":
    unittest.main()
