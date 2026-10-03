from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PREVIEW = GODOT / "world_map_preview.gd"
PROCEDURAL = GODOT / "world_map_perceptual_vegetation.gd"
HERO = GODOT / "world_map_perceptual_assets.gd"


class PerceptualLodHandoff008BNTests(unittest.TestCase):
    def test_procedural_nearfield_moves_out_only_with_vendor_assets(self) -> None:
        source = PROCEDURAL.read_text(encoding="utf-8")
        self.assertIn("func set_hero_nearfield_enabled(enabled: bool)", source)
        self.assertIn("_tree_inner_m = 25.0", source)
        self.assertIn("_undergrowth_inner_m = 20.0", source)
        self.assertIn("_tree_inner_m = INNER_M + 3.0", source)
        self.assertIn("_undergrowth_inner_m = INNER_M", source)
        self.assertIn("var radius := lerpf(_tree_inner_m, OUTER_M, radial_ratio)", source)
        self.assertIn(
            "var radius := lerpf(_undergrowth_inner_m, OUTER_M * 0.82, radial_ratio)",
            source,
        )

    def test_preview_builds_vendor_layer_before_deciding_handoff(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        assets_build = source.index("_perceptual_assets.build()")
        handoff = source.index("_perceptual_vegetation.set_hero_nearfield_enabled(")
        procedural_build = source.index("_perceptual_vegetation.build(")
        self.assertLess(assets_build, handoff)
        self.assertLess(handoff, procedural_build)
        self.assertIn("_perceptual_assets.vendor_ready()", source)

    def test_hero_log_is_change_driven(self) -> None:
        source = HERO.read_text(encoding="utf-8")
        self.assertIn('var _last_logged_region := ""', source)
        self.assertIn("var _last_logged_counts := Vector3i(-1, -1, -1)", source)
        self.assertIn("or counts != _last_logged_counts", source)
        self.assertIn("or tree_name != _last_logged_tree_asset", source)
        self.assertIn("or understory_name != _last_logged_understory_asset", source)

    def test_budgets_are_unchanged(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        procedural = PROCEDURAL.read_text(encoding="utf-8")
        self.assertIn("const TREE_BUDGET := 14", hero)
        self.assertIn("const UNDERSTORY_BUDGET := 40", hero)
        self.assertIn("const ROCK_BUDGET := 18", hero)
        self.assertIn("const TREE_BUDGET := 72", procedural)
        self.assertIn("const UNDERGROWTH_BUDGET := 320", procedural)


if __name__ == "__main__":
    unittest.main()
