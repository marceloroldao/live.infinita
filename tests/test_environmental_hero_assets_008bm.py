from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps" / "renderer-godot"
MODULE = GODOT / "world_map_perceptual_assets.gd"
PREVIEW = GODOT / "world_map_preview.gd"


class EnvironmentalHeroAssets008BMTests(unittest.TestCase):
    def test_budgets_are_intentionally_small(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("const TREE_BUDGET := 14", source)
        self.assertIn("const UNDERSTORY_BUDGET := 40", source)
        self.assertIn("const ROCK_BUDGET := 18", source)
        self.assertIn("const OUTER_M := 31.0", source)
        self.assertIn("const INNER_M := 6.5", source)

    def test_environment_selects_real_asset_classes(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        for asset in (
            "CommonTree_1.gltf",
            "Pine_1.gltf",
            "Bush_Common.gltf",
            "Grass_Common_Tall.gltf",
            "Rock_Medium_1.gltf",
        ):
            self.assertIn(asset, source)
        self.assertIn('climate in ["cool_montane", "alpine_cold"]', source)
        self.assertIn('zone in ["meadow", "wetland", "alpine_meadow"]', source)
        self.assertIn('environment.get("rock_exposure"', source)
        self.assertIn('environment.get("tree_suitability"', source)
        self.assertIn('environment.get("vegetation_density"', source)

    def test_import_cache_guard_prevents_broken_dynamic_load(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("func _import_cache_ready(path: String) -> bool:", source)
        self.assertIn('config.get_value("remap", "path", "")', source)
        self.assertIn("FileAccess.file_exists(remap_path)", source)
        self.assertIn("if not _import_cache_ready(path) or not ResourceLoader.exists(path):", source)
        guard = source[source.index("if not _vendor_ready:"):source.index("if not force", source.index("if not _vendor_ready:"))]
        self.assertIn("visible_instance_count = 0", guard)
        self.assertIn("return", guard)

    def test_hero_layer_is_multimesh_and_visual_only(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("MultiMesh.new()", source)
        self.assertIn("MultiMeshInstance3D.new()", source)
        self.assertNotIn("StaticBody3D", source)
        self.assertNotIn("CollisionShape3D", source)
        self.assertNotIn("GuardedMutationService", source)
        self.assertNotIn("move_and_slide", source)

    def test_preview_orchestrates_hero_assets(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn(
            'PerceptualAssets = preload("res://world_map_perceptual_assets.gd")',
            source,
        )
        self.assertIn("_perceptual_assets = PerceptualAssets.new(", source)
        self.assertIn("_perceptual_assets.build()", source)
        self.assertIn("_perceptual_assets.update_environment(environmental_state)", source)
        self.assertIn("_perceptual_assets.rebuild(", source)
        self.assertLess(len(source), 36000)


if __name__ == "__main__":
    unittest.main()
