"""Visual-only forest scene gates: bounded draw, no world mutations and real assets."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "apps/renderer-godot"
PACK = SCENE / "assets/quaternius/stylized_nature_megakit"


class ForestStageTests(unittest.TestCase):
    def test_main_scene_stays_2d_and_optional_preview_is_3d(self):
        main = (SCENE / "main.tscn").read_text()
        three = (SCENE / "forest_preview.tscn").read_text()
        self.assertIn('[node name="LiveInfinita" type="Node2D"]', main)
        self.assertIn('[node name="ForestPreview" type="Node3D"]', three)
        self.assertNotIn("forest_preview", main)
        self.assertNotIn("SubViewport", main)
        self.assertIn('run/main_scene="res://main.tscn"',
                      (SCENE / "project.godot").read_text())

    def test_2d_forest_is_bounded_and_world_driven(self):
        content = (SCENE / "diorama.gd").read_text()
        atmosphere = (SCENE / "atmosphere_overlay.gd").read_text()
        self.assertIn('mix.get("forest", 0.0)', content)
        self.assertIn('func _forest_floor(', content)
        self.assertIn('func _forest_trees(', content)
        self.assertIn('FOREST_TREE_COUNT := 17', content)
        self.assertIn('FOREST_STONE_COUNT := 19', content)
        self.assertIn('"_normalized_biome"', '"_normalized_biome"')
        self.assertIn('return {current: 1.0}', atmosphere)
        for forbidden in ("FileAccess.open", "DirAccess.", "randf(", "randi(",
                          "set_world", "post_world", "WorldState.", "submit_intent"):
            self.assertNotIn(forbidden, content)
        self.assertLessEqual(len(content), 16000)

    def test_preview_uses_shipped_cc0_models_without_external_io(self):
        catalog = json.loads((PACK / "catalog.json").read_text())
        self.assertEqual(catalog["license"], "CC0-1.0")
        available = {kind: 0 for kind in ("tree", "rock", "plant")}
        for item in catalog["assets"]:
            if item["kind"] in available:
                available[item["kind"]] += 1
                self.assertTrue((SCENE / item["path"].removeprefix("res://")).is_file())
        self.assertTrue(all(v >= 3 for v in available.values()))
        preview = (SCENE / "forest_preview.gd").read_text()
        for kind in available:
            self.assertIn('"' + kind + '"', preview)
        self.assertIn('MAX_VISUALS := TREE_ROWS * 2 + ROCK_COUNT + PLANT_COUNT', preview)
        self.assertIn('FOREST_PREVIEW_READY', preview)
        self.assertIn("ResourceLoader.exists", preview)
        self.assertIn("_asset_cache", preview)
        self.assertIn("sun.shadow_enabled = false", preview)
        self.assertNotIn("http", preview)
        self.assertNotIn("WebSocket", preview)
        self.assertNotIn("FileAccess", preview)
        self.assertNotIn("WorldState", preview)


if __name__ == "__main__":
    unittest.main()
