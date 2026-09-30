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

    def test_preserves_cold_world_contract(self):
        text = (ROOT / "docs/PERSISTENT_REGIONS_LONG_TRAVEL_001.md").read_text()
        self.assertIn("HOT <= 96", text)
        self.assertIn("WARM <= 192", text)
        self.assertTrue((SCENE / "nature_asset_catalog.gd").exists())


if __name__ == "__main__":
    unittest.main()
