from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / "apps" / "renderer-godot" / "world_map_live_visual.gd"


class RegionVisualBatching008AITests(unittest.TestCase):
    def test_region_labels_are_bounded(self) -> None:
        source = VISUAL.read_text(encoding="utf-8")
        self.assertIn("const MAX_REGION_LABELS := 4", source)
        self.assertIn("if labels >= MAX_REGION_LABELS:", source)
        self.assertIn('label.name = "RegionLabel_"', source)

    def test_rings_share_at_most_two_surfaces(self) -> None:
        source = VISUAL.read_text(encoding="utf-8")
        section = source[source.index("func _build_region_rings"):source.index("func _region_label")]
        self.assertIn("Mesh.PRIMITIVE_LINES", section)
        self.assertIn('"RegionRings"', section)
        self.assertIn("var normal_regions: Array = []", section)
        self.assertIn("var current_regions: Array = []", section)
        self.assertNotIn('"RegionRing_"', section)

    def test_world_region_count_is_not_reduced_by_label_budget(self) -> None:
        source = VISUAL.read_text(encoding="utf-8")
        section = source[source.index("func update_regions"):]
        self.assertIn("selected.size()", section)
        self.assertIn("return selected.size()", section)
        self.assertIn("WORLD_MAP_REGION_VISUAL", section)


if __name__ == "__main__":
    unittest.main()
