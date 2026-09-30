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
        self.assertEqual(data["grid_size"], 32)
        self.assertEqual(data["tile_size_m"], 64)
        self.assertEqual(data["grid_size"] ** 2, 1024)
        self.assertEqual(data["grid_size"] * data["tile_size_m"], 2048)
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
        self.assertGreaterEqual(len(ids), 11)
        for expected in ("waterfall_overlook", "watchtower", "stone_circle", "cave", "meadow", "ruins"):
            self.assertIn(expected, ids)
        self.assertEqual(data["start"], [10, 15])

    def test_two_kilometer_layout_preserves_central_coordinates(self):
        data = json.loads(MAP.read_text(encoding="utf-8"))
        half = data["grid_size"] * data["tile_size_m"] / 2

        def center(cell):
            return (
                (cell[0] + 0.5) * data["tile_size_m"] - half,
                (cell[1] + 0.5) * data["tile_size_m"] - half,
            )

        landmarks = {item["id"]: item for item in data["landmarks"]}
        self.assertEqual(center(landmarks["shelter"]["cell"]), (-352.0, -32.0))
        self.assertEqual(center(landmarks["old_grove"]["cell"]), (-160.0, -32.0))
        self.assertEqual(center(landmarks["river_crossing"]["cell"]), (32.0, -32.0))
        self.assertEqual(center(landmarks["village"]["cell"]), (224.0, 96.0))
        distant = [center(landmarks[key]["cell"]) for key in ("ruins", "watchtower", "stone_circle", "cave", "meadow")]
        self.assertTrue(any(abs(x) > 512 or abs(z) > 512 for x, z in distant))
        layout = (SCENE / "world_map_layout.gd").read_text(encoding="utf-8")
        preview = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("half_m = float(grid_size) * tile_size_m * 0.5", layout)
        self.assertNotIn("const GRID := 16", preview)
        self.assertNotIn("const HALF :=", preview)

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
        self.assertIn('cx == _cell_for_world(RIVER_X)', features)
        self.assertIn('func _special_landmark(', features)
        for feature in ("RuinsWallA", "WatchtowerBase", "StandingStone_", "CaveSideA", "MeadowMast", "WaterfallSheet"):
            self.assertIn(feature, features)
        self.assertIn('for index in range(steps):', features)
        self.assertIn('maxf(a.x, b.x)', features)
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

    def test_persistent_region_overlay_and_collision_budget(self):
        feed = (SCENE / "world_map_live_feed.gd").read_text(encoding="utf-8")
        visual = (SCENE / "world_map_live_visual.gd").read_text(encoding="utf-8")
        features = (SCENE / "world_map_features.gd").read_text(encoding="utf-8")
        self.assertIn("region_descriptors", feed)
        self.assertIn("MAX_LOCAL_REGIONS := 16", visual)
        self.assertIn("REGION_RING_SEGMENTS := 48", visual)
        self.assertIn("func update_regions(", visual)
        self.assertIn("ImmediateMesh.new()", visual)
        self.assertIn("MAX_COLLIDERS_PER_TILE := 3", features)
        self.assertIn("StaticBody3D.new()", features)
        self.assertIn("BoxShape3D.new()", features)
        self.assertIn('_solid_box(tile, "BridgeRail"', features)
        self.assertIn('_solid_box(root, "Walls"', features)

    def test_local_traversability_is_physical_read_only_and_bounded(self):
        traversal = (SCENE / "world_map_traversability.gd").read_text(encoding="utf-8")
        motion = (SCENE / "world_map_local_motion.gd").read_text(encoding="utf-8")
        hud = (SCENE / "world_map_hud.gd").read_text(encoding="utf-8")
        preview = SCRIPT.read_text(encoding="utf-8")
        for required in (
            'RIVER_HALF_WIDTH := 10.0', 'BRIDGE_HALF_WIDTH := 3.1',
            'MAX_STEP_M := 1.25', 'MAX_COLLISION_HITS := 8',
            'river_without_bridge', 'static_obstacle', 'intersect_shape',
        ):
            self.assertIn(required, traversal)
        for required in (
            'CharacterBody3D.new()', 'move_and_slide()', 'BODY_CENTER_Y := 0.9',
            'LocalExplorerBody', 'validate_step(current, candidate, space_state)',
        ):
            self.assertIn(required, motion)
        self.assertIn('LocalMotion = preload("res://world_map_local_motion.gd")', preview)
        self.assertIn('Hud = preload("res://world_map_hud.gd")', preview)
        self.assertIn('Layout = preload("res://world_map_layout.gd")', preview)
        self.assertIn('_layout.half_m', preview)
        self.assertIn('var _half_m := 512.0', traversal)
        self.assertIn('get_world_3d().direct_space_state', preview)
        self.assertIn('EXPLORAR LOCAL', hud)
        self.assertIn('VOLTAR AO NOV', hud)
        self.assertIn('nao move NOV', hud)
        self.assertIn('Input.action_press(action)', hud)
        self.assertIn('_last_live_position', preview)
        self.assertIn('_on_local_mode', preview)
        for source in (traversal, motion, hud):
            for forbidden in (
                "WebSocket", "HTTPClient", "FileAccess", "DirAccess",
                "send_text", "send_json", "submit_intent", "post_world",
            ):
                self.assertNotIn(forbidden, source)
        self.assertTrue((ROOT / "tests/godot_world_map_traversal_smoke.gd").exists())

    def test_web_rollout_is_separate_and_atomic(self):
        rollout = (ROOT / "deploy/export-world-map-preview-web.sh").read_text()
        self.assertIn('PREVIEW_NAME="world-map-preview"', rollout)
        self.assertIn('run/main_scene="res://world_map_preview.tscn"', rollout)
        self.assertIn('TARGET="$WEB_ROOT/$PREVIEW_NAME"', rollout)
        self.assertIn('.world-map-preview.stage.', rollout)
        self.assertIn('/godot/world-map-preview/', rollout)
        self.assertIn('/nov-preview/', rollout)
        self.assertIn('SMOKE_TEST="$SOURCE_DIR/tests/godot_world_map_traversal_smoke.gd"', rollout)
        self.assertIn('World-map traversal smoke: 0 failures', rollout)
        self.assertIn('"traversability": "local-physics-read-only"', rollout)
        self.assertIn('"touch_controls": true', rollout)
        for required in ("world_map_hud.gd", "world_map_local_motion.gd", "world_map_traversability.gd", "world_map_layout.gd"):
            self.assertIn(required, rollout)
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
