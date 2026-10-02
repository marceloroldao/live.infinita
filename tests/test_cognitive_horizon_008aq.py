from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"
TERRAIN = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"

class DistantCognitiveMassifs008AQTests(unittest.TestCase):
    def test_camera_reaches_distant_cognitive_relief(self) -> None:
        preview = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const CAMERA_FAR_M := 620.0", preview)
        self.assertIn("_camera.far = CAMERA_FAR_M", preview)
        self.assertNotIn("WorldHorizonGround", preview)

    def test_massifs_are_more_legible_without_more_massifs(self) -> None:
        terrain = TERRAIN.read_text(encoding="utf-8")
        self.assertIn("const MAX_MASSIFS := 6", terrain)
        self.assertIn("const MAX_MASSIF_HEIGHT_M := 92.0", terrain)
        self.assertIn("influence_radius * 0.40", terrain)
        self.assertIn("32.0, 90.0", terrain)
        self.assertIn("bias * 2.8 + mass * 32.0", terrain)

if __name__ == "__main__":
    unittest.main()
