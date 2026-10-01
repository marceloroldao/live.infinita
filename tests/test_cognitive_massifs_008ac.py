from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class CognitiveMassifs008ACTests(unittest.TestCase):
    def test_massifs_are_bounded_visual_meshes(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        self.assertIn("const MAX_MASSIFS := 6", source)
        self.assertIn("const MAX_MASSIF_HEIGHT_M := 68.0", source)
        self.assertIn("const MASSIF_MIN_BIAS_M := 6.0", source)
        self.assertIn("const MASSIF_MIN_MASS := 0.55", source)
        self.assertIn("func _rebuild_massifs(height_sampler: Callable) -> void:", source)
        self.assertIn('peak.name = "MemoryMassif_%s_%s"', source)
        self.assertIn("mesh.radial_segments = 9", source)
        self.assertNotIn(
            "StaticBody3D.new()",
            source[source.index("func _massif_material"):source.index("func _trail_batch_material")],
        )

    def test_massif_does_not_amplify_height_delta(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        height_section = source[source.index("func height_delta"):]
        self.assertNotIn("MAX_MASSIF_HEIGHT_M", height_section)
        self.assertNotIn("_rebuild_massifs", height_section)
        self.assertIn("return clampf(total, MAX_BASIN_M, MAX_UPLIFT_M)", height_section)

    def test_runtime_log_exposes_massif_count(self) -> None:
        preview = PREVIEW.read_text(encoding="utf-8")
        self.assertIn(
            "WORLD_MAP_MEMORY_TERRAIN projection=%s lakes=%d trails=%d trail_batches=%d massifs=%d",
            preview,
        )
        self.assertIn("_cognitive_terrain.trail_batch_count()", preview)
        self.assertIn("_cognitive_terrain.massif_count()", preview)


if __name__ == "__main__":
    unittest.main()
