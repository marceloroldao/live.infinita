from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"


class NovPerceptualCamera008BGTests(unittest.TestCase):
    def test_camera_defaults_to_close_third_person(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        for expected in (
            "const CAMERA_FOV_DEG := 64.0",
            "const CAMERA_BACK_M := 6.4",
            "const CAMERA_HEIGHT_M := 3.0",
            "const CAMERA_LOOK_HEIGHT_M := 1.25",
            "const CAMERA_MIN_GROUND_CLEARANCE_M := 1.9",
            "const PERCEPTUAL_CAMERA_ENABLED := true",
        ):
            self.assertIn(expected, source)
        self.assertIn("_camera.fov = CAMERA_FOV_DEG", source)
        self.assertIn("- forward * CAMERA_BACK_M", source)
        self.assertIn("camera_ground + CAMERA_MIN_GROUND_CLEARANCE_M", source)

    def test_camera_follows_observed_and_local_motion_heading(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        self.assertIn("_update_camera_heading(_last_live_position, projected)", source)
        self.assertIn("_update_camera_heading(previous_position, _position)", source)
        self.assertIn("_orient_nov_visual()", source)
        self.assertIn("CAMERA_HEADING_BLEND", source)

    def test_presentation_hides_map_diagnostic_overlays(self) -> None:
        preview = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        visual = (GODOT / "world_map_live_visual.gd").read_text(encoding="utf-8")
        self.assertIn("const SHOW_DIAGNOSTIC_WORLD_OVERLAYS := false", preview)
        self.assertIn(
            "_live_visual.set_diagnostic_overlays(SHOW_DIAGNOSTIC_WORLD_OVERLAYS)",
            preview,
        )
        self.assertIn("func set_diagnostic_overlays(enabled: bool)", visual)
        self.assertIn("if not _diagnostic_overlays_enabled:", visual)


if __name__ == "__main__":
    unittest.main()
