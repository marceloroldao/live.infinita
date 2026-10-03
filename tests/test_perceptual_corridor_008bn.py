from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "renderer-godot" / "world_map_perceptual_assets.gd"


class PerceptualCorridor008BNTests(unittest.TestCase):
    def test_corridor_constants_are_bounded(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("const CORRIDOR_LENGTH_M := 28.0", source)
        self.assertIn("const CORRIDOR_TREE_ROCK_HALF_WIDTH_M := 3.8", source)
        self.assertIn("const CORRIDOR_UNDERSTORY_HALF_WIDTH_M := 1.9", source)

    def test_tree_rock_and_understory_use_corridor_guard(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            source.count("CORRIDOR_TREE_ROCK_HALF_WIDTH_M"),
            3,
        )
        self.assertGreaterEqual(
            source.count("CORRIDOR_UNDERSTORY_HALF_WIDTH_M"),
            2,
        )
        self.assertIn("func _inside_corridor(", source)
        self.assertIn("var longitudinal := delta.dot(flat_forward)", source)
        self.assertIn("var lateral := absf(delta.dot(right))", source)

    def test_hero_rocks_are_slightly_smaller(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("var scale := 0.48 + 0.48 * noise", source)

    def test_hero_logging_is_deduplicated(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn('var _last_logged_signature := ""', source)
        self.assertIn("if signature != _last_logged_signature:", source)
        self.assertIn("_last_logged_signature = signature", source)


if __name__ == "__main__":
    unittest.main()
