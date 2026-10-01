from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class MemoryTrailCorridors008AATests(unittest.TestCase):
    def test_trails_clear_center_and_shape_edges(self) -> None:
        terrain = TERRAIN.read_text(encoding="utf-8")
        preview = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("func _trail_decor_profile(point: Vector2) -> Dictionary:", terrain)
        self.assertIn('"role": "trail_corridor"', terrain)
        self.assertIn('"role": "trail_edge"', terrain)
        self.assertIn('if role == "trail_edge" and influence >= 0.15', preview)
        self.assertIn('kind = "rock" if index % 4 == 0 else "plant"', preview)

    def test_corridors_remain_visual_only(self) -> None:
        terrain = TERRAIN.read_text(encoding="utf-8")
        corridor_start = terrain.index("func _trail_decor_profile")
        surface_start = terrain.index("func surface_at")
        height_start = terrain.index("func height_delta")
        corridor_section = terrain[corridor_start:height_start]
        self.assertNotIn("world.json", corridor_section)
        self.assertNotIn("GuardedMutationService", corridor_section)
        self.assertNotIn("set_collision", corridor_section)
        self.assertNotIn("_trail_decor_profile", terrain[height_start:])
        self.assertLess(surface_start, corridor_start)


if __name__ == "__main__":
    unittest.main()
