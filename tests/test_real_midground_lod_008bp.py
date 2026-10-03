from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
HERO = GODOT / "world_map_perceptual_assets.gd"
PROCEDURAL = GODOT / "world_map_perceptual_vegetation.gd"
ASSETS = GODOT / "assets" / "quaternius" / "stylized_nature_megakit" / "models" / "glTF"


def triangle_count(name: str) -> int:
    data = json.loads((ASSETS / name).read_text(encoding="utf-8"))
    total = 0
    for mesh in data.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            accessor = primitive.get("indices")
            if isinstance(accessor, int):
                total += int(data["accessors"][accessor].get("count", 0)) // 3
    return total


class RealMidgroundLOD008BPTests(unittest.TestCase):
    def test_midground_uses_lighter_real_tree_variants(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        self.assertIn('COMMON_TREE_MID := ASSET_BASE + "CommonTree_5.gltf"', hero)
        self.assertIn('PINE_TREE_MID := ASSET_BASE + "Pine_5.gltf"', hero)
        self.assertLess(triangle_count("CommonTree_5.gltf"), triangle_count("CommonTree_1.gltf"))
        self.assertLess(triangle_count("Pine_5.gltf"), triangle_count("Pine_1.gltf"))

    def test_three_tree_lod_bands_overlap_without_gap(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        procedural = PROCEDURAL.read_text(encoding="utf-8")
        for expected in (
            "const OUTER_M := 31.0",
            "const MID_TREE_INNER_M := 30.0",
            "const MID_TREE_OUTER_M := 58.0",
        ):
            self.assertIn(expected, hero)
        self.assertIn("const TREE_INNER_M := 50.0", procedural)
        self.assertIn("const TREE_OUTER_M := 90.0", procedural)

    def test_real_midground_budget_is_small_and_procedural_budget_is_reduced(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        procedural = PROCEDURAL.read_text(encoding="utf-8")
        self.assertIn("const MID_TREE_BUDGET := 18", hero)
        self.assertIn('"MidNatureTrees"', hero)
        self.assertIn("const TREE_BUDGET := 44", procedural)
        self.assertIn("const UNDERGROWTH_BUDGET := 220", procedural)
        self.assertIn("const UNDERGROWTH_INNER_M := 28.0", procedural)

    def test_midground_keeps_environment_and_corridor_rules(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        section = hero[hero.index("var mid_tree_count := 0"):hero.index("var understory_count := 0")]
        self.assertIn("_candidate_position(", section)
        self.assertIn("MID_TREE_INNER_M", section)
        self.assertIn("MID_TREE_OUTER_M", section)
        self.assertIn("_allowed_sampler.call(p.x, p.y)", section)
        self.assertIn("_inside_corridor(", section)
        self.assertIn("CORRIDOR_TREE_ROCK_HALF_WIDTH_M", section)

    def test_midground_is_visual_only_multimesh(self) -> None:
        hero = HERO.read_text(encoding="utf-8")
        self.assertIn("MultiMeshInstance3D", hero)
        self.assertNotIn("StaticBody3D", hero)
        self.assertNotIn("CollisionShape3D", hero)
        self.assertNotIn("GuardedMutationService", hero)


if __name__ == "__main__":
    unittest.main()
