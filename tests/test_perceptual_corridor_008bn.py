from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "renderer-godot" / "world_map_perceptual_assets.gd"


class PerceptualCorridor008BNTests(unittest.TestCase):


    def test_hero_rocks_are_slightly_smaller(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("scale = 0.48 + 0.48 * noise", source)

    def test_hero_logging_is_deduplicated(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn('var _last_logged_signature := ""', source)
        self.assertIn("if signature != _last_logged_signature:", source)
        self.assertIn("_last_logged_signature = signature", source)


if __name__ == "__main__":
    unittest.main()
