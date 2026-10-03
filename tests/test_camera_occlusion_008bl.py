from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PREVIEW = GODOT / "world_map_preview.gd"
FEATURES = GODOT / "world_map_features.gd"


class CameraOcclusion008BLTests(unittest.TestCase):
    def test_presentation_hides_world_labels(self) -> None:
        preview = PREVIEW.read_text(encoding="utf-8")
        features = FEATURES.read_text(encoding="utf-8")
        self.assertIn("const SHOW_WORLD_LABELS := false", preview)
        self.assertIn("_features.set_landmark_markers_visible(SHOW_WORLD_LABELS)", preview)
        self.assertIn("func set_landmark_markers_visible(visible: bool)", features)
        self.assertIn("if not _show_landmark_markers:", features)
        self.assertIn("return", features[features.index("func _landmark"):features.index("func _special_landmark")])

    def test_camera_raycast_uses_existing_collision_layer(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("func _follow_camera"):source.index("func _update_caption")]
        self.assertIn("PhysicsRayQueryParameters3D.create(pivot, camera_position, 1)", section)
        self.assertIn("direct_space_state.intersect_ray(query)", section)
        self.assertIn("const CAMERA_COLLISION_MARGIN_M := 0.55", source)
        self.assertIn("camera_position = hit_position + toward_pivot * CAMERA_COLLISION_MARGIN_M", section)

    def test_waterfall_keeps_visual_name_and_gains_collider(self) -> None:
        source = FEATURES.read_text(encoding="utf-8")
        section = source[source.index('"waterfall":'):source.index("func _init", source.index('"waterfall":'))]
        self.assertIn("_solid_box(", section)
        self.assertIn('"WaterfallSheet"', section)
        self.assertNotIn('_box(tile, "WaterfallSheet"', section)

    def test_feature_physics_contract_remains_layer_one_default(self) -> None:
        source = FEATURES.read_text(encoding="utf-8")
        solid = source[source.index("func _solid_box"):source.index("func _path")]
        self.assertIn("StaticBody3D.new()", solid)
        self.assertNotIn("collision_layer =", solid)
        self.assertNotIn("collision_mask =", solid)


if __name__ == "__main__":
    unittest.main()
