from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class DecorDistanceCulling008AGTests(unittest.TestCase):
    def test_bounded_ranges_are_explicit(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const TREE_VISIBILITY_RANGE_M := 145.0", source)
        self.assertIn("const ROCK_VISIBILITY_RANGE_M := 110.0", source)
        self.assertIn("const PLANT_VISIBILITY_RANGE_M := 82.0", source)
        self.assertIn("const DECOR_VISIBILITY_MARGIN_M := 12.0", source)

    def test_culling_is_applied_to_geometry_instances_only(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("func _apply_decor_culling"):source.index("func _decoration")]
        self.assertIn("if node is GeometryInstance3D:", section)
        self.assertIn("visibility_range_end = range_end", section)
        self.assertIn("visibility_range_end_margin = DECOR_VISIBILITY_MARGIN_M", section)
        self.assertIn("VISIBILITY_RANGE_FADE_DISABLED", section)
        self.assertNotIn("queue_free()", section)

    def test_world_authority_is_untouched(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("func _decor_visibility_range"):source.index("func _prune_tile_cache")]
        self.assertNotIn("world.json", section)
        self.assertNotIn("GuardedMutationService", section)
        self.assertNotIn("StaticBody3D.new()", section)
        self.assertIn("WORLD_MAP_DECOR_CULL", section)


if __name__ == "__main__":
    unittest.main()
