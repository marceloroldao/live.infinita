from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PROCEDURAL = GODOT / "world_map_perceptual_vegetation.gd"
HERO = GODOT / "world_map_perceptual_assets.gd"


class PerceptualLODSeparation008BOTests(unittest.TestCase):
    def test_procedural_layer_starts_beyond_hero_foreground(self) -> None:
        source = PROCEDURAL.read_text(encoding="utf-8")
        self.assertIn("const TREE_INNER_M := 50.0", source)
        self.assertIn("const TREE_OUTER_M := 90.0", source)
        self.assertIn("const UNDERGROWTH_INNER_M := 28.0", source)
        self.assertIn("const UNDERGROWTH_OUTER_M := 64.0", source)
        self.assertIn("lerpf(TREE_INNER_M, TREE_OUTER_M, radial_ratio)", source)
        self.assertIn("UNDERGROWTH_INNER_M, UNDERGROWTH_OUTER_M", source)

    def test_hero_and_procedural_layers_have_small_transition_overlap(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        procedural = PROCEDURAL.read_text(encoding="utf-8")
        self.assertIn("const OUTER_M := 31.0", hero)
        self.assertIn("const MID_TREE_INNER_M := 30.0", hero)
        self.assertIn("const MID_TREE_OUTER_M := 58.0", hero)
        self.assertIn("const TREE_INNER_M := 50.0", procedural)
        self.assertIn("const UNDERGROWTH_INNER_M := 28.0", procedural)

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
