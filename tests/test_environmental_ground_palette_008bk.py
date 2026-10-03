from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PALETTE = GODOT / "world_map_environmental_palette.gd"
TERRAIN = GODOT / "world_map_cognitive_terrain.gd"
PREVIEW = GODOT / "world_map_preview.gd"


class EnvironmentalGroundPalette008BKTests(unittest.TestCase):
    def test_palette_is_visual_only_and_bounded(self) -> None:
        source = PALETTE.read_text(encoding="utf-8")
        self.assertIn("extends RefCounted", source)
        self.assertIn("func terrain_color(", source)
        for field in (
            'environment.get("vegetation_density"',
            'environment.get("soil_moisture"',
            'environment.get("rock_exposure"',
            'environment.get("snow_cover"',
            'environment.get("ecological_zone"',
            'environment.get("cognitive_influence"',
        ):
            self.assertIn(field, source)
        for forbidden in (
            "GuardedMutationService",
            "CharacterBody3D",
            "MeshInstance3D.new()",
            "FileAccess",
            "HTTPClient",
            "WebSocket",
        ):
            self.assertNotIn(forbidden, source)

    def test_cognitive_terrain_resolves_environment_by_actual_anchor(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        section = source[source.index("func environment_at"):source.index("func surface_at")]
        self.assertIn("_environment_by_region.get(region_id", section)
        self.assertIn('anchor.get("region_id"', section)
        self.assertIn("point.distance_squared_to(pos)", section)
        self.assertIn('"cognitive_influence"', section)
        self.assertNotIn("world_write", section)

    def test_preview_applies_palette_to_horizon_and_active_tiles(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn(
            'EnvironmentalPalette = preload("res://world_map_environmental_palette.gd")',
            source,
        )
        self.assertIn("_environmental_palette = EnvironmentalPalette.new()", source)
        self.assertIn('call("environment_at", x, z)', source)
        self.assertIn("_environmental_palette.horizon_base(y)", source)
        self.assertIn("st.set_color(_environmental_color(", source)
        self.assertIn("_environmental_color(_terrain_color(biome), center.x, center.y)", source)
        self.assertLess(len(source), 36000)

    def test_no_new_render_batches_are_added_by_palette(self) -> None:
        source = PALETTE.read_text(encoding="utf-8")
        self.assertNotIn("MultiMesh", source)
        self.assertNotIn("SurfaceTool", source)
        self.assertNotIn("add_child", source)


if __name__ == "__main__":
    unittest.main()
