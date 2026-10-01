from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"


class CognitiveEcology008QTests(unittest.TestCase):
    def test_cognitive_terrain_exposes_bounded_decor_profile(self) -> None:
        source = (GODOT / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn("func decor_profile_at(x: float, z: float) -> Dictionary:", source)
        self.assertIn('"allow_decor": false', source)
        self.assertIn('"role": "lake"', source)
        self.assertIn('"influence": clampf(best_influence, 0.0, 1.0)', source)

    def test_preview_never_places_static_decor_in_cognitive_water(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        profile_idx = source.index("var profile: Dictionary = _cognitive_terrain.decor_profile_at(x, z)")
        reject_idx = source.index('if not bool(profile.get("allow_decor", true)):', profile_idx)
        pick_idx = source.index('var chosen: Dictionary = _catalog.call("pick"', profile_idx)
        self.assertLess(profile_idx, reject_idx)
        self.assertLess(reject_idx, pick_idx)

    def test_uplift_and_basin_have_different_visual_ecology(self) -> None:
        source = (GODOT / "world_map_preview.gd").read_text(encoding="utf-8")
        self.assertIn('if role == "uplift":', source)
        self.assertIn('elif role == "basin":', source)
        self.assertIn('kind = "rock" if index % 3 == 0 else "tree"', source)
        self.assertIn('kind = "rock" if index % 3 == 0 else "plant"', source)

    def test_ecology_remains_visual_only(self) -> None:
        source = (GODOT / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn("# Visual-only projection of bounded Memoria.ia aggregates.", source)
        self.assertNotIn("GuardedMutationService", source)
        self.assertNotIn("world.json", source)


if __name__ == "__main__":
    unittest.main()
