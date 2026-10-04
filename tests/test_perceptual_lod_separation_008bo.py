from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PROCEDURAL = GODOT / "world_map_perceptual_vegetation.gd"
HERO = GODOT / "world_map_perceptual_assets.gd"


class PerceptualLODSeparation008BOTests(unittest.TestCase):


    def test_budgets_do_not_increase(self) -> None:
        source = PROCEDURAL.read_text(encoding="utf-8")
        self.assertIn("const TREE_BUDGET := 44", source)
        self.assertIn("const UNDERGROWTH_BUDGET := 220", source)

    def test_procedural_layer_remains_multimesh_only(self) -> None:
        source = PROCEDURAL.read_text(encoding="utf-8")
        self.assertNotIn("StaticBody3D", source)
        self.assertNotIn("CollisionShape3D", source)
        self.assertNotIn("ResourceLoader", source)


if __name__ == "__main__":
    unittest.main()
