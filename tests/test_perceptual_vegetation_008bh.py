from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PREVIEW = GODOT / "world_map_preview.gd"
MODULE = GODOT / "world_map_perceptual_vegetation.gd"


class PerceptualVegetation008BHTests(unittest.TestCase):
    def test_local_vegetation_is_bounded_and_batched(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        for expected in (
            "const TREE_BUDGET := 44",
            "const UNDERGROWTH_BUDGET := 220",
            "const TREE_INNER_M := 50.0",
            "const TREE_OUTER_M := 90.0",
            "const UNDERGROWTH_INNER_M := 28.0",
            "const UNDERGROWTH_OUTER_M := 64.0",
            '"PerceptualTreeTrunks"',
            '"PerceptualTreeCanopies"',
            '"PerceptualUndergrowth"',
        ):
            self.assertIn(expected, source)
        self.assertIn("_batch_factory.call(", source)
        self.assertNotIn("CollisionShape3D", source)
        self.assertNotIn("StaticBody3D", source)
        self.assertNotIn("ResourceLoader", source)

    def test_environment_controls_local_density(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        for field in (
            'environment.get("vegetation_density"',
            'environment.get("tree_suitability"',
            'environment.get("rock_exposure"',
            'environment.get("snow_cover"',
            'environment.get("ecological_zone"',
        ):
            self.assertIn(field, source)
        for expected in (
            'forest_affinity',
            'meadow_affinity',
            'shrub_affinity',
            'wetland_affinity',
            'alpine_affinity',
            'tree_membership := clampf(',
            'undergrowth_membership := clampf(',
        ):
            self.assertIn(expected, source)
        self.assertNotIn("zone_tree_multiplier", source)

    def test_only_local_forward_volume_is_materialized(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("HALF_ANGLE_RAD", source)
        self.assertIn("forward.normalized()", source)
        self.assertIn("REBUILD_DISTANCE_M", source)
        self.assertIn("REBUILD_DOT", source)
        self.assertIn("_allowed_sampler.call(x, z)", source)
        self.assertIn("visible_instance_count = tree_placed", source)
        self.assertIn("visible_instance_count = undergrowth_placed", source)

    def test_preview_only_orchestrates_perceptual_module(self) -> None:
        preview = PREVIEW.read_text(encoding="utf-8")
        self.assertIn(
            'const PerceptualVegetation = preload("res://world_map_perceptual_vegetation.gd")',
            preview,
        )
        self.assertIn("_perceptual_vegetation = PerceptualVegetation.new(", preview)
        self.assertIn("_perceptual_vegetation.update_environment(environmental_state)", preview)
        self.assertIn("_perceptual_vegetation.rebuild(", preview)
        self.assertNotIn("func _environmental_vegetation_factors", preview)
        self.assertLess(len(preview), 36000)

    def test_last_valid_environmental_region_survives_feed_gap(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn('var _last_region_id := ""', source)
        self.assertIn('if not region_id.is_empty():', source)
        self.assertIn('_last_region_id = region_id', source)
        self.assertIn('effective_region_id := region_id if not region_id.is_empty() else _last_region_id', source)
        self.assertIn('const REBUILD_DISTANCE_M := 10.0', source)
        self.assertIn('const REBUILD_DOT := 0.94', source)

    def test_camera_is_tighter_than_008bg(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const CAMERA_FOV_DEG := 64.0", source)
        self.assertIn("const CAMERA_BACK_M := 6.4", source)
        self.assertIn("const CAMERA_HEIGHT_M := 3.0", source)
        self.assertIn("const CAMERA_MIN_GROUND_CLEARANCE_M := 1.9", source)


if __name__ == "__main__":
    unittest.main()
