from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"


class CognitiveWaterLevel008BTTests(unittest.TestCase):
    def test_lake_level_uses_sampled_basin_height(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("const LAKE_SURFACE_ABOVE_BASIN_M := 1.05", source)
        self.assertIn("const LAKE_FALLBACK_Y_M := -1.55", source)
        self.assertIn("func _rebuild_lakes(height_sampler: Callable = Callable())", source)
        self.assertIn("var basin_y := float(height_sampler.call(pos.x, pos.y))", source)
        self.assertIn("water_y = basin_y + LAKE_SURFACE_ABOVE_BASIN_M", source)
        self.assertNotIn('lake.position = Vector3(pos.x, -1.55, pos.y)', source)

    def test_update_passes_same_height_sampler_to_lake_massif_and_trail(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        update = source[source.index("func update("):source.index("func _material")]
        self.assertIn("_rebuild_lakes(height_sampler)", update)
        self.assertIn("_rebuild_massifs(height_sampler)", update)
        self.assertIn("_rebuild_trails(height_sampler)", update)

    def test_water_level_change_is_visual_only(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        section = source[source.index("func _rebuild_lakes"):source.index("func _massif_environment")]
        for forbidden in ("CharacterBody3D", "move_and_slide", "GuardedMutationService", "FileAccess", "HTTPClient"):
            self.assertNotIn(forbidden, section)


if __name__ == "__main__":
    unittest.main()
