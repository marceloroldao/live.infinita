from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
PREVIEW = GODOT / "world_map_preview.gd"
MODULE = GODOT / "world_map_distant_relief.gd"


class DistantRelief008BRTests(unittest.TestCase):
    def test_relief_is_visual_only_and_distance_gated(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        for expected in (
            "const ENABLED := true",
            "const START_M := 180.0",
            "const FULL_M := 360.0",
            "const SCALE := 1.55",
            "const MAX_VISUAL_DELTA_M := 18.0",
            "func height_for(",
            "func visual_height(",
        ):
            self.assertIn(expected, source)
        self.assertIn("distance_m <= START_M", source)
        self.assertIn("t = t * t * (3.0 - 2.0 * t)", source)
        self.assertIn("clampf(extra, -MAX_VISUAL_DELTA_M, MAX_VISUAL_DELTA_M)", source)
        for forbidden in ("CharacterBody3D", "StaticBody3D", "CollisionShape3D", "GuardedMutationService"):
            self.assertNotIn(forbidden, source)

    def test_walkable_terrain_remains_raw_height(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        local_vertex = source[source.index("func _vertex"):source.index("func _terrain(")]
        horizon_vertex = source[source.index("func _horizon_vertex"):source.index("func _rebuild_horizon_ground")]
        self.assertIn("st.add_vertex(Vector3(x, _height(x, z), z))", local_vertex)
        self.assertNotIn("_distant_relief", local_vertex)
        self.assertIn("_distant_relief.visual_height(_height(x, z), x, z)", horizon_vertex)

    def test_preview_only_orchestrates_relief_module(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn(
            'const DistantRelief = preload("res://world_map_distant_relief.gd")',
            source,
        )
        self.assertIn("_distant_relief = DistantRelief.new()", source)
        self.assertIn(
            "_distant_relief.update_observer(_position, _height(_position.x, _position.z))",
            source,
        )
        self.assertLess(len(source), 36000)

    def test_cell_changes_refresh_visual_horizon(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("_rebuild_horizon_ground()"), 4)


if __name__ == "__main__":
    unittest.main()
