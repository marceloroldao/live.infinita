"""Canonical preview topology must match the authoritative region graph."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "apps/renderer-godot"


class NovWorldTopologyTests(unittest.TestCase):
    def setUp(self):
        self.topology = json.loads((SCENE / "nov_world_topology_001.json").read_text())
        self.projection = json.loads((SCENE / "nov_map_projection_001.json").read_text())
        self.visual_map = json.loads((SCENE / "world_map_001.json").read_text())

    def test_authoritative_region_graph_is_exact_and_symmetric(self):
        topo = self.topology
        self.assertEqual(topo["schema"], "live-infinita-nov-world-map-topology/v1")
        self.assertEqual(topo["world_id"], "nov-live-autonomous-001")
        self.assertTrue(topo["preview_only"])
        regions = topo["authoritative_regions"]
        self.assertEqual(set(regions), {"shelter", "clearing", "deep_forest"})
        self.assertEqual(regions["shelter"]["neighbors"], ["clearing"])
        self.assertEqual(set(regions["clearing"]["neighbors"]), {"shelter", "deep_forest"})
        self.assertEqual(regions["deep_forest"]["neighbors"], ["clearing"])
        self.assertNotIn("deep_forest", regions["shelter"]["neighbors"])
        normalized = {tuple(sorted(edge)) for edge in topo["authoritative_edges"]}
        self.assertEqual(normalized, {("clearing", "shelter"), ("clearing", "deep_forest")})
        for region_id, region in regions.items():
            for neighbor in region["neighbors"]:
                self.assertIn(region_id, regions[neighbor]["neighbors"])

    def test_projection_anchors_are_derived_from_same_authored_topology(self):
        for region_id, region in self.topology["authoritative_regions"].items():
            anchor = self.projection["anchors"][region_id]
            self.assertEqual(anchor["world_center"], region["world_center"])
            self.assertEqual(anchor["map_cell"], region["map_cell"])
        self.assertEqual(self.projection["anchors"]["shelter"]["map_cell"], [2, 7])
        self.assertEqual(self.projection["anchors"]["clearing"]["map_cell"], [5, 7])
        self.assertEqual(self.projection["anchors"]["deep_forest"]["map_cell"], [5, 4])

    def test_visual_route_respects_authoritative_y_before_fictional_expansion(self):
        route = self.visual_map["route"]
        self.assertEqual(route[:4], [[2, 7], [5, 7], [5, 4], [5, 7]])
        landmarks = {item["id"]: item["cell"] for item in self.visual_map["landmarks"]}
        self.assertEqual(landmarks["shelter"], [2, 7])
        self.assertEqual(landmarks["central_clearing"], [5, 7])
        self.assertEqual(landmarks["deep_forest"], [5, 4])
        self.assertEqual(set(self.topology["visual_expansion_regions"]), {"river", "village", "hills"})

    def test_world_facts_remain_separate_from_visual_expansion(self):
        regions = set(self.topology["authoritative_regions"])
        expansion = set(self.topology["visual_expansion_regions"])
        self.assertTrue(regions.isdisjoint(expansion))
        self.assertNotIn("river", regions)
        self.assertNotIn("village", regions)
        self.assertNotIn("hills", regions)


if __name__ == "__main__":
    unittest.main()
