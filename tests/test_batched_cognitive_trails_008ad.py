from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class BatchedCognitiveTrails008ADTests(unittest.TestCase):
    def test_trails_use_one_surface_batch(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        section = source[source.index("func _rebuild_trails"):source.index("func surface_at")]
        self.assertIn("var surface := SurfaceTool.new()", section)
        self.assertIn('trail_batch.name = "MemoryTrailBatch"', section)
        self.assertIn("_trail_batch_count = 1", section)
        self.assertNotIn("BoxMesh.new()", section)
        self.assertNotIn('trail.name = "MemoryTrail_', section)

    def test_batch_material_avoids_transparent_per_segment_draws(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        section = source[source.index("func _trail_batch_material"):source.index("func _trail_orientation_sign")]
        self.assertIn("vertex_color_use_as_albedo = true", section)
        self.assertIn("SHADING_MODE_UNSHADED", section)
        self.assertIn("CULL_DISABLED", section)
        self.assertNotIn("TRANSPARENCY_ALPHA", section)

    def test_runtime_log_exposes_batch_count(self) -> None:
        preview = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("trail_batches=%d", preview)
        self.assertIn("_cognitive_terrain.trail_batch_count()", preview)


if __name__ == "__main__":
    unittest.main()
