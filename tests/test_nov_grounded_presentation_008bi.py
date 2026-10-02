from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"


class NovGroundedPresentation008BITests(unittest.TestCase):
    def test_camera_looks_ahead_into_world(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        self.assertIn("const CAMERA_LOOK_AHEAD_M := 11.0", source)
        self.assertIn("const CAMERA_LOOK_HEIGHT_M := 1.35", source)
        self.assertIn("+ forward * CAMERA_LOOK_AHEAD_M", source)
        self.assertNotIn(
            "var target := _position + Vector3(0, CAMERA_LOOK_HEIGHT_M, 0)",
            source,
        )

    def test_local_physics_uses_nov_visual_without_changing_collision(self) -> None:
        source = (GODOT / "world_map_local_motion.gd").read_text(encoding="utf-8")
        self.assertIn('NovCharacterVisual = preload("res://nov_character_visual.gd")', source)
        self.assertIn("var visual := NovCharacterVisual.new()", source)
        self.assertIn('visual.name = "NovVisual"', source)
        self.assertNotIn('visual.name = "NovVisualMarker"', source)
        self.assertIn("var shape := CapsuleShape3D.new()", source)
        self.assertIn("shape.radius = 0.44", source)
        self.assertIn("shape.height = 1.8", source)

    def test_fallback_nov_is_low_poly_humanoid_and_visual_only(self) -> None:
        source = (GODOT / "nov_character_visual.gd").read_text(encoding="utf-8")
        for part in ("Torso", "Head", "PrimitiveWrap", "ArmL", "ArmR", "LegL", "LegR", "Hair"):
            self.assertIn(f'"{part}"', source)
        self.assertIn("SHADING_MODE_PER_VERTEX", source)
        self.assertNotIn("CharacterBody3D", source)
        self.assertNotIn("move_and_slide", source)
        self.assertIn("Never writes World State", source)


if __name__ == "__main__":
    unittest.main()
