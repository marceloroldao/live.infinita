from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "cognitive_terrain_projection.py"
spec = importlib.util.spec_from_file_location("cognitive_terrain_projection_008r", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

REGIONS = [
    {"region_id": "a", "center": {"x": 0.0, "y": 0.0}, "biome": "forest"},
    {"region_id": "b", "center": {"x": 100.0, "y": 0.0}, "biome": "hills"},
    {"region_id": "c", "center": {"x": 200.0, "y": 0.0}, "biome": "meadow"},
]


def projection(records):
    return module.build_projection(
        world_id="w", known_regions=REGIONS, records=records,
        source_snapshot_records=len(records), checkpoint_cursor=len(records),
    )


class CognitiveTrails008RTests(unittest.TestCase):
    def test_recent_repeated_transition_becomes_trail(self) -> None:
        p = projection([
            {"logical_tick": 10, "region_id": "a", "need": "explore"},
            {"logical_tick": 20, "region_id": "b", "need": "explore"},
            {"logical_tick": 30, "region_id": "a", "need": "explore"},
            {"logical_tick": 40, "region_id": "b", "need": "explore"},
        ])
        edges = {(r["from_region_id"], r["to_region_id"]): r for r in p["transitions"]}
        edge = edges[("a", "b")]
        self.assertEqual(edge["count"], 2)
        self.assertEqual(edge["last_logical_tick"], 40)
        self.assertTrue(edge["trail_candidate"])
        self.assertGreaterEqual(edge["trail_strength"], 0.99)
        self.assertGreater(edge["trail_width_m"], 2.0)

    def test_old_repeated_transition_fades(self) -> None:
        p = projection([
            {"logical_tick": 10, "region_id": "a", "need": "explore"},
            {"logical_tick": 20, "region_id": "b", "need": "explore"},
            {"logical_tick": 30, "region_id": "a", "need": "explore"},
            {"logical_tick": 40, "region_id": "b", "need": "explore"},
            {"logical_tick": 1000, "region_id": "c", "need": "explore"},
        ])
        edges = {(r["from_region_id"], r["to_region_id"]): r for r in p["transitions"]}
        edge = edges[("a", "b")]
        self.assertEqual(edge["count"], 2)
        self.assertFalse(edge["trail_candidate"])
        self.assertLess(edge["trail_strength"], 0.18)
        self.assertLess(edge["recency_strength"], 0.18)

    def test_renderer_bounds_and_fades_trail_visuals(self) -> None:
        source = (ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn("const MAX_TRAIL_SEGMENTS := 192", source)
        self.assertIn("func _rebuild_trails(height_sampler: Callable) -> void:", source)
        self.assertIn('int(ridge.get("count", 0)) < 2', source)
        self.assertIn('intensity < 0.18', source)
        self.assertIn("material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA", source)
        self.assertIn("height_sampler.call(center.x, center.y)", source)
    def test_trails_remain_visual_side_channel_only(self) -> None:
        terrain = (ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        projection_source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("# Visual-only projection of bounded Memoria.ia aggregates.", terrain)
        self.assertNotIn("GuardedMutationService", terrain)
        self.assertNotIn("world.json", terrain)
        self.assertIn('"world_write_authority": False', projection_source)
        self.assertIn('"selection_authority": False', projection_source)


if __name__ == "__main__":
    unittest.main()
