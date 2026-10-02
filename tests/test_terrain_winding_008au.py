from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class TerrainWinding008AUTests(unittest.TestCase):
    def test_first_triangle_faces_up_in_macro_and_local_terrain(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        macro = """_horizon_vertex(st, x, z)
            _horizon_vertex(st, x + step, z)
            _horizon_vertex(st, x, z + step)
            _horizon_vertex(st, x + step, z)
            _horizon_vertex(st, x + step, z + step)
            _horizon_vertex(st, x, z + step)"""
        local = """_vertex(st, x, z)
            _vertex(st, x + step, z)
            _vertex(st, x, z + step)
            _vertex(st, x + step, z)
            _vertex(st, x + step, z + step)
            _vertex(st, x, z + step)"""
        self.assertIn(macro, source)
        self.assertIn(local, source)

    def test_normals_are_height_gradient_driven(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const TERRAIN_NORMAL_SAMPLE_M := 4.0", source)
        self.assertIn("func _terrain_normal(x: float, z: float) -> Vector3:", source)
        self.assertIn("st.set_normal(_terrain_normal(x, z))", source)
        terrain_section = source[source.index("func _horizon_vertex"):source.index("func _decor_visibility_range")]
        self.assertNotIn("generate_normals()", terrain_section)

    def test_materials_keep_backface_culling_enabled(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertNotIn("CULL_DISABLED", source[source.index("func _material"):source.index("func _height")])


if __name__ == "__main__":
    unittest.main()
