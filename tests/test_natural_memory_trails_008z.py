from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"


class NaturalMemoryTrails008ZTests(unittest.TestCase):
    def test_renderer_uses_deterministic_naturalized_points(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        self.assertIn("const MAX_TRAIL_MEANDER_M := 4.5", source)
        self.assertIn("func _natural_trail_point(", source)
        self.assertIn("func _trail_seed(a: Vector2, b: Vector2) -> float:", source)
        self.assertIn("_natural_trail_point(a, b, t0, count, intensity)", source)
        self.assertIn("_natural_trail_point(a, b, t1, count, intensity)", source)
        self.assertNotIn("randf(", source)
        self.assertNotIn("randi(", source)

    def test_naturalization_remains_visual_only(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        self.assertIn("# Visual-only projection of bounded Memoria.ia aggregates.", source)
        self.assertNotIn("world.json", source)
        self.assertNotIn("GuardedMutationService", source)
        self.assertNotIn("_natural_trail_point(", source[source.index("func height_delta"):])

    def test_recurrence_straightens_visual_path(self) -> None:
        source = TERRAIN.read_text(encoding="utf-8")
        self.assertIn("amplitude *= lerpf(1.0, 0.58, recurrence)", source)
        self.assertIn("amplitude *= lerpf(1.0, 0.72, strength)", source)


if __name__ == "__main__":
    unittest.main()
