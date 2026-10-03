from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"


class ImmersivePresentation008BJTests(unittest.TestCase):
    def test_camera_uses_small_shoulder_offset(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        self.assertIn("const CAMERA_SHOULDER_M := 0.95", source)
        self.assertIn("var right := Vector3(-forward.z, 0.0, forward.x).normalized()", source)
        self.assertIn("+ right * CAMERA_SHOULDER_M", source)

    def test_technical_status_is_hidden_but_controls_remain(self) -> None:
        preview = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        hud = (GODOT / "world_map_hud.gd").read_text(encoding="utf-8")
        self.assertIn("const SHOW_TECHNICAL_STATUS := false", preview)
        self.assertIn("_hud.set_technical_status_visible(SHOW_TECHNICAL_STATUS)", preview)
        self.assertIn("func set_technical_status_visible(visible: bool)", hud)
        self.assertIn("_status.visible = visible", hud)
        self.assertIn('Button.new()', hud)
        self.assertIn('"EXPLORAR LOCAL"', hud)

    def test_fallback_humanoid_uses_tapered_low_poly_body(self) -> None:
        source = (GODOT / "nov_character_visual.gd").read_text(encoding="utf-8")
        torso = source[source.index("var torso_mesh"):source.index("var head_mesh")]
        hip = source[source.index("var hip_mesh"):source.index("for side in")]
        self.assertIn("CylinderMesh.new()", torso)
        self.assertIn("top_radius = 0.27", torso)
        self.assertIn("bottom_radius = 0.36", torso)
        self.assertIn("radial_segments = 6", torso)
        self.assertIn("CylinderMesh.new()", hip)
        self.assertNotIn("BoxMesh.new()", torso + hip)

    def test_tree_instances_vary_width_and_height_without_more_batches(self) -> None:
        source = (GODOT / "world_map_perceptual_vegetation.gd").read_text(encoding="utf-8")
        self.assertIn("var height_scale :=", source)
        self.assertIn("var trunk_width :=", source)
        self.assertIn("var canopy_width :=", source)
        self.assertIn("var trunk_basis :=", source)
        self.assertIn("var canopy_basis :=", source)
        self.assertIn("Vector3(trunk_width, height_scale, trunk_width)", source)
        self.assertIn("Vector3(canopy_width, height_scale, canopy_width)", source)
        self.assertIn("const TREE_BUDGET := 44", source)
        self.assertIn("const UNDERGROWTH_BUDGET := 220", source)


if __name__ == "__main__":
    unittest.main()
