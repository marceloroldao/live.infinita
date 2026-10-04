from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"


class CognitiveRidgeVisuals008BVTests(unittest.TestCase):
    def test_ranges_are_bounded_and_batched(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for expected in (
            "const MAX_RIDGE_RANGES := 6",
            "const RIDGE_RANGE_MIN_HEIGHT_M := 3.5",
            "const RIDGE_RANGE_MIN_STRENGTH := 0.35",
            "const RIDGE_RANGE_VISIBILITY_BEGIN_M := 90.0",
            "const RIDGE_RANGE_MAX_VISUAL_HEIGHT_M := 28.0",
            'range_batch.name = "MemoryRidgeRangeBatch"',
            "_ridge_range_count = built_ranges",
        ):
            self.assertIn(expected, source)
        self.assertEqual(source.count('"MemoryRidgeRangeBatch"'), 1)

    def test_only_strong_cognitive_ridges_become_ranges(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        section = source[
            source.index("func _rebuild_ridge_ranges"):
            source.index("func _trail_batch_material")
        ]
        self.assertIn('ridge.get("height", 0.0)', section)
        self.assertIn("RIDGE_RANGE_MIN_HEIGHT_M", section)
        self.assertIn('ridge.get("strength", 0.0)', section)
        self.assertIn("RIDGE_RANGE_MIN_STRENGTH", section)
        self.assertIn("_ridge_range_score", section)
        self.assertIn("MAX_RIDGE_RANGES", section)

    def test_ranges_keep_region_identity_for_environmental_color(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('"from_region_id": from_id', source)
        self.assertIn('"to_region_id": to_id', source)
        self.assertIn('ridge.get("from_region_id", "")', source)
        self.assertIn('ridge.get("to_region_id", "")', source)
        self.assertIn('environment.get("rock_exposure"', source)
        self.assertIn('environment.get("snow_cover"', source)

    def test_range_geometry_is_visual_only(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        section = source[
            source.index("func _ridge_range_material"):
            source.index("func _trail_batch_material")
        ]
        self.assertIn("SurfaceTool.new()", section)
        self.assertIn("MeshInstance3D.new()", section)
        for forbidden in (
            "StaticBody3D",
            "CollisionShape3D",
            "CharacterBody3D",
            "move_and_slide",
            "GuardedMutationService",
        ):
            self.assertNotIn(forbidden, section)


if __name__ == "__main__":
    unittest.main()
