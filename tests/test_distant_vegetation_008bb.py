from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class DistantVegetation008BBTests(unittest.TestCase):
    def test_budget_is_bounded_and_batched(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const DISTANT_VEGETATION_COUNT := 120", source)
        self.assertIn("const DISTANT_VEGETATION_INNER_M := 96.0", source)
        self.assertIn("const DISTANT_VEGETATION_OUTER_M := 390.0", source)
        self.assertIn("MultiMeshInstance3D", source)
        self.assertIn('DistantTreeTrunks', source)
        self.assertIn('DistantTreeCanopies', source)
        self.assertIn("BaseMaterial3D.SHADING_MODE_UNSHADED", source)

    def test_distant_vegetation_has_no_collision_or_asset_instances(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("func _distant_material"):source.index("func _height")]
        self.assertNotIn("StaticBody3D", section)
        self.assertNotIn("CollisionShape3D", section)
        self.assertNotIn("ResourceLoader", section)
        self.assertNotIn(".instantiate()", section)

    def test_rebuild_is_event_driven_not_per_frame(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        process = source[source.index("func _process"):]

        self.assertIn("_rebuild_distant_vegetation()", source)
        self.assertIn("if old_cell != Vector2i", process)
        # It may be called inside the cell-change branch, but not unconditionally
        # before that branch.
        prefix = process.split("if old_cell != Vector2i", 1)[0]
        self.assertNotIn("_rebuild_distant_vegetation()", prefix)


if __name__ == "__main__":
    unittest.main()
