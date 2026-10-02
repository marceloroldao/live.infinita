from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class MidgroundVegetation008BDTests(unittest.TestCase):
    def test_midground_budget_is_bounded_and_batched(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const MIDGROUND_VEGETATION_COUNT := 180", source)
        self.assertIn("const MIDGROUND_VEGETATION_INNER_M := 16.0", source)
        self.assertIn("const MIDGROUND_VEGETATION_OUTER_M := 94.0", source)
        self.assertIn('"MidgroundVegetation"', source)
        self.assertIn("MIDGROUND_VEGETATION_COUNT", source)
        self.assertIn("func _new_vegetation_batch(", source)

    def test_midground_respects_memory_decor_policy(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("func _midground_allowed"):source.index("func _height")]
        self.assertIn('decor_profile_at', section)
        self.assertIn('not bool(profile.get("allow_decor", true))', section)
        self.assertIn('_biome(_cell(x), _cell(z)) == "river"', section)

    def test_midground_is_visual_only(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("func _build_midground_vegetation"):source.index("func _height")]
        self.assertNotIn("StaticBody3D", section)
        self.assertNotIn("CollisionShape3D", section)
        self.assertNotIn(".instantiate()", section)
        self.assertNotIn("ResourceLoader", section)


if __name__ == "__main__":
    unittest.main()
