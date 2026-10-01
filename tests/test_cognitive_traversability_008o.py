from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"


class CognitiveTraversability008OTests(unittest.TestCase):
    def test_cognitive_terrain_exposes_read_only_surface_policy(self) -> None:
        source = (GODOT / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn("func surface_at(x: float, z: float) -> Dictionary:", source)
        self.assertIn('"reason": "cognitive_lake"', source)
        self.assertIn('"surface": "water"', source)
        self.assertNotIn("GuardedMutationService", source)
        self.assertNotIn("FileAccess", source)

    def test_traversability_accepts_dynamic_surface_without_owning_memory(self) -> None:
        source = (GODOT / "world_map_traversability.gd").read_text(encoding="utf-8")
        self.assertIn("dynamic_surface: Callable = Callable()", source)
        self.assertIn("_dynamic_surface.call(position.x, position.z)", source)
        self.assertNotIn("cognitive_terrain", source)
        self.assertNotIn("Memoria", source)

    def test_local_motion_passes_dynamic_policy_to_traversability(self) -> None:
        source = (GODOT / "world_map_local_motion.gd").read_text(encoding="utf-8")
        self.assertIn("dynamic_surface: Callable = Callable()", source)
        self.assertIn("Traversability.new(walk_height, half_m, dynamic_surface)", source)

    def test_preview_wires_cognitive_surface_into_local_explorer(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        self.assertIn('Callable(_cognitive_terrain, "surface_at")', source)

    def test_lake_visual_and_collision_policy_share_geometry(self) -> None:
        source = (GODOT / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        radius_expr = 'minf(68.0, float(anchor.get("radius", 120.0)) * 0.38)'
        self.assertGreaterEqual(source.count(radius_expr), 2)
        self.assertGreaterEqual(source.count('float(anchor.get("bias", 0.0))'), 2)


if __name__ == "__main__":
    unittest.main()
