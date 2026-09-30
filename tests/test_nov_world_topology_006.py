from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "examples" / "nov-world-regions-005.json"
MAP = ROOT / "apps" / "renderer-godot" / "world_map_001.json"
MODULE = ROOT / "deploy" / "nov_world_topology_006.py"

spec = importlib.util.spec_from_file_location("nov_world_topology_006_test", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NovWorldTopology006Test(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = json.loads(TOPOLOGY.read_text(encoding="utf-8"))
        self.map = json.loads(MAP.read_text(encoding="utf-8"))
        self.regions = {row["id"]: row for row in self.topology["regions"]}
        self.landmarks = {row["id"]: row for row in self.map["landmarks"]}

    def test_topology_is_connected_symmetric_and_has_expected_regions(self) -> None:
        self.assertEqual(len(self.regions), 12)
        expected = {
            "clearing", "shelter", "deep_forest", "river_crossing", "village", "ridge",
            "waterfall_overlook", "watchtower", "stone_circle", "cave", "meadow", "ruins",
        }
        self.assertEqual(set(self.regions), expected)
        for region_id, row in self.regions.items():
            for neighbor in row["neighbors"]:
                self.assertIn(neighbor, self.regions)
                self.assertIn(region_id, self.regions[neighbor]["neighbors"])

        visited = set()
        pending = ["clearing"]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(self.regions[current]["neighbors"])
        self.assertEqual(visited, expected)

    def test_existing_centers_are_unchanged(self) -> None:
        self.assertEqual(self.regions["clearing"]["center"], {"x": 640.0, "y": 360.0})
        self.assertEqual(self.regions["shelter"]["center"], {"x": 930.0, "y": 390.0})
        self.assertEqual(self.regions["deep_forest"]["center"], {"x": 350.0, "y": 340.0})

    def _map_center(self, landmark_id: str) -> tuple[float, float]:
        cell = self.landmarks[landmark_id]["cell"]
        half = self.map["grid_size"] * self.map["tile_size_m"] / 2.0
        return (
            (cell[0] + 0.5) * self.map["tile_size_m"] - half,
            (cell[1] + 0.5) * self.map["tile_size_m"] - half,
        )

    def _project(self, x: float, y: float) -> tuple[float, float]:
        p = self.map["runtime_projection"]
        wa = p["world_anchor_a"]
        wb = p["world_anchor_b"]
        ma = p["map_anchor_a_m"]
        mb = p["map_anchor_b_m"]

        wax, way = float(wa[0]), float(wa[1])
        world_dx, world_dy = float(wb[0]) - wax, float(wb[1]) - way
        world_len = math.hypot(world_dx, world_dy)
        wu = (world_dx / world_len, world_dy / world_len)
        wp = (-wu[1], wu[0])

        map_dx, map_dy = float(mb[0]) - float(ma[0]), float(mb[1]) - float(ma[1])
        map_len = math.hypot(map_dx, map_dy)
        mu = (map_dx / map_len, map_dy / map_len)
        mp = (-mu[1], mu[0])
        scale = map_len / world_len

        ox, oy = x - wax, y - way
        along = ox * wu[0] + oy * wu[1]
        across = ox * wp[0] + oy * wp[1]
        return (
            float(ma[0]) + mu[0] * along * scale + mp[0] * across * scale,
            float(ma[1]) + mu[1] * along * scale + mp[1] * across * scale,
        )

    def test_runtime_centers_project_onto_map_landmarks(self) -> None:
        for region in self.regions.values():
            landmark_id = region.get("metadata", {}).get("map_landmark_id")
            if not landmark_id:
                continue
            projected = self._project(region["center"]["x"], region["center"]["y"])
            expected = self._map_center(landmark_id)
            self.assertAlmostEqual(projected[0], expected[0], places=4, msg=region["id"])
            self.assertAlmostEqual(projected[1], expected[1], places=4, msg=region["id"])

    def test_apply_is_canonical_replayable_and_survives_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = module.apply_topology(
                topology_file=TOPOLOGY,
                bootstrap_file=ROOT / "examples" / "world-state.nov-live.bootstrap.json",
                data_dir=root / "data",
                cold_store_dir=root / "cold",
            )
            self.assertEqual(result["status"], "applied")
            self.assertEqual(result["regions_total"], 12)
            engine = module.ColdAuthoritativeWorldEngine(
                ROOT / "examples" / "world-state.nov-live.bootstrap.json",
                root / "data",
                module.FileRegionColdStore(root / "cold"),
            )
            self.assertTrue(engine.verify_replay()["ok"])
            _, _, reset_world = engine.commit_action("reset")
            self.assertEqual(len(reset_world["regions"]), 12)
            self.assertIn("cave", {row["id"] for row in reset_world["regions"]})
            self.assertTrue(engine.verify_replay()["ok"])

    def test_root_rollout_is_transactional_and_snapshot_verified(self) -> None:
        rollout = (ROOT / "deploy" / "nov-world-topology-006-root.sh").read_text(encoding="utf-8")
        for required in (
            "flock -x 9",
            "verify_snapshot",
            "write_old_topology",
            "--replace-exact",
            "deploy-nov-topology-006-rollback",
            "systemctl stop live-infinita-autonomous-world.service live-infinita.service",
            "systemctl restart live-infinita-autonomous-world.service live-infinita.service",
            "TOPOLOGY_WORLD_OK",
            "TOPOLOGY_API_OK",
        ):
            self.assertIn(required, rollout)
        self.assertNotIn("sed -i", rollout)
        self.assertNotIn("jq '.regions", rollout)

    def test_merge_preserves_dynamic_regions_and_neighbor_links(self) -> None:
        current = json.loads(json.dumps(self.topology["regions"]))
        current[0]["neighbors"].append("collective_moon_001")
        current.append({
            "id": "collective_moon_001",
            "center": {"x": 700.0, "y": 700.0},
            "radius": 90.0,
            "biome": "forest",
            "neighbors": ["clearing"],
            "metadata": {"collective": True},
        })
        merged = module.merge_regions(current, self.topology["regions"])
        by_id = {row["id"]: row for row in merged}
        self.assertIn("collective_moon_001", by_id)
        self.assertIn("collective_moon_001", by_id["clearing"]["neighbors"])
        self.assertTrue(by_id["collective_moon_001"]["metadata"]["collective"])


if __name__ == "__main__":
    unittest.main()
