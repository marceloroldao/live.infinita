from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"


class EnvironmentalRendering008BFTests(unittest.TestCase):
    def test_live_feed_carries_environmental_state(self) -> None:
        feed = (GODOT / "world_map_live_feed.gd").read_text(encoding="utf-8")
        preview = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        self.assertIn("environmental_state: Dictionary", feed)
        self.assertIn('delivery.get("environmental_state", {})', feed)
        self.assertIn("Dictionary(environmental_state).duplicate(true)", feed)
        self.assertIn("environmental_state: Dictionary = {}", preview)
        self.assertIn("environmental_state\n    ))", preview)

    def test_cognitive_shape_and_environmental_appearance_are_separate(self) -> None:
        terrain = (GODOT / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn('const ENVIRONMENT_SCHEMA := "live-infinita-environmental-state/v1"', terrain)
        self.assertIn("var _environment_state_id :=", terrain)
        self.assertIn("next_environment_id == _environment_state_id", terrain)
        self.assertIn('environment.get("rock_exposure"', terrain)
        self.assertIn('environment.get("snow_cover"', terrain)
        self.assertIn('environment.get("vegetation_density"', terrain)
        self.assertIn('"MemorySnowCap_%s_%s"', terrain)

    def test_snow_caps_are_bounded_to_primary_massif_peaks(self) -> None:
        terrain = (GODOT / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn("if not secondary and snow_cover >= 0.12:", terrain)
        self.assertIn("cap_fraction := clampf", terrain)
        self.assertIn("cap_mesh.radial_segments = 9", terrain)
        self.assertIn("func snow_cap_count() -> int:", terrain)


if __name__ == "__main__":
    unittest.main()
