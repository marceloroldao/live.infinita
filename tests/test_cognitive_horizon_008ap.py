from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class CognitiveHorizon008APTests(unittest.TestCase):
    def test_horizon_is_one_bounded_plane_and_extended_camera(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const CAMERA_FAR_M := 620.0", source)
        self.assertIn("const HORIZON_GROUND_MARGIN_M := 256.0", source)
        self.assertIn('horizon_ground.name = "WorldHorizonGround"', source)
        self.assertIn("var horizon_mesh := PlaneMesh.new()", source)
        self.assertIn("_camera.far = CAMERA_FAR_M", source)
        self.assertEqual(source.count("WorldHorizonGround"), 1)

    def test_horizon_does_not_expand_active_tile_budget(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const MAX_ACTIVE_TILES := 9", source)
        self.assertIn("const MAX_ACTIVE_DECOR := 22", source)


if __name__ == "__main__":
    unittest.main()
