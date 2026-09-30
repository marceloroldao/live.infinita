"""Contract tests for read-only Vale de Nov spatial projection and bridge route."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from packages.spatial.world_map_navigation import (
    BRIDGE_CELL, MAP_FRAME, WorldMapNavigation,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "apps/renderer-godot/world_map_001.json"


class WorldMapNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.navigator = WorldMapNavigation(json.loads(MANIFEST.read_text(encoding="utf-8")))

    def test_stable_256_cells_and_exact_coordinate_bounds(self):
        nav = self.navigator
        ids = {nav.cell_id((x, z)) for x in range(16) for z in range(16)}
        self.assertEqual(len(ids), 256)
        self.assertEqual(nav.position_cell(-512.0, -512.0), (0, 0))
        self.assertEqual(nav.position_cell(511.999, 511.999), (15, 15))
        self.assertEqual(nav.position_cell(512.0, 0), None)
        self.assertEqual(nav.position_cell(0, -513), None)
        self.assertEqual(nav.position_cell(float("nan"), 1), None)
        self.assertEqual(nav.position_cell(True, 0), None)
        for x in range(16):
            for z in range(16):
                self.assertEqual(nav.position_cell(*nav.coordinates((x, z))), (x, z))

    def test_local_materialization_never_exceeds_nine_cells(self):
        nav = self.navigator
        for x in range(16):
            for z in range(16):
                px, pz = nav.coordinates((x, z))
                active = nav.active_cells(px, pz)
                self.assertLessEqual(len(active), 9)
                self.assertGreaterEqual(len(active), 4)
                self.assertIn((x, z), active)
                self.assertEqual(len(set(active)), len(active))
        self.assertEqual(nav.active_cells(700, 0), ())

    def test_only_bridge_cell_crosses_river(self):
        nav = self.navigator
        self.assertEqual(nav.biome(BRIDGE_CELL), "river")
        self.assertTrue(nav.accessible(BRIDGE_CELL))
        for z in range(16):
            if z != BRIDGE_CELL[1]:
                self.assertFalse(nav.accessible((8, z)))
        for landmark in ("village", "ridge"):
            path = nav.path_to_landmark(nav.landmarks["shelter"], landmark)
            self.assertTrue(path)
            self.assertIn(BRIDGE_CELL, path)
            self.assertTrue(all(nav.accessible(cell) for cell in path))
            self.assertEqual(path[0], nav.landmarks["shelter"])
            self.assertEqual(path[-1], nav.landmarks[landmark])
            for a, b in zip(path, path[1:]):
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)

    def test_old_world_and_unbound_nov_never_claim_position(self):
        nav = self.navigator
        old = {"entities": [{"id": "nov", "region_id": "clearing",
                             "position": {"x": 360, "y": 300}}]}
        self.assertEqual(nav.project_nov(old)["reason"], "coordinate_frame_not_bound")
        self.assertEqual(nav.project_nov({"entities": []})["reason"], "nov_not_materialized")
        self.assertEqual(nav.project_nov({})["reason"], "no_entities")
        old["entities"][0]["position_frame"] = MAP_FRAME
        self.assertEqual(nav.project_nov(old)["reason"], "region_position_mismatch")

    def test_explicitly_bound_nov_projects_without_world_mutation(self):
        nav = self.navigator
        cell = nav.landmarks["old_grove"]
        x, z = nav.coordinates(cell)
        nov = {"id": "nov", "position_frame": MAP_FRAME,
               "region_id": nav.cell_id(cell), "position": {"x": x, "y": z}}
        world = {"entities": [nov]}
        before = json.dumps(world, sort_keys=True)
        view = nav.project_nov(world)
        self.assertEqual(view["status"], "read_only")
        self.assertEqual(view["cell"], list(cell))
        self.assertEqual(view["region_id"], nav.cell_id(cell))
        self.assertLessEqual(view["active_count"], 9)
        self.assertFalse(view["world_mutated"])
        self.assertFalse(view["selection_authority"])
        self.assertEqual(json.dumps(world, sort_keys=True), before)

    def test_reject_bad_manifest(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        data["landmarks"][0]["cell"] = [99, 0]
        with self.assertRaises(ValueError):
            WorldMapNavigation(data)
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        data["landmarks"][1]["id"] = data["landmarks"][0]["id"]
        with self.assertRaises(ValueError):
            WorldMapNavigation(data)


if __name__ == "__main__":
    unittest.main()
