from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class TileDecorLod008ADTests(unittest.TestCase):
    def test_lod_budget_reduces_far_decor_only(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const CENTER_DECOR_INDICES := [0, 1, 2, 3, 4, 5]", source)
        self.assertIn("const EDGE_DECOR_INDICES := [0, 2, 4]", source)
        self.assertIn("const CORNER_DECOR_INDICES := [1]", source)
        self.assertIn("const MAX_ACTIVE_DECOR := 22", source)
        self.assertIn("func _decor_indices_for_tile(", source)
        self.assertIn("dx + dz == 1", source)

    def test_central_visual_density_is_preserved(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("source: Array = CENTER_DECOR_INDICES", source)
        self.assertIn("_layout.decorations_per_tile", source)
        self.assertIn("for i in decor_indices:", source)

    def test_lod_does_not_touch_terrain_or_motion(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        helper = source[source.index("func _decor_indices_for_tile"):source.index("func _sync_tiles")]
        self.assertNotIn("_height(", helper)
        self.assertNotIn("_local_motion", helper)
        self.assertNotIn("_cognitive_terrain", helper)


if __name__ == "__main__":
    unittest.main()
