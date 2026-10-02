from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class TerrainWinding008AUTests(unittest.TestCase):
    def test_first_triangle_faces_up_in_macro_and_local_terrain(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        macro = """_horizon_vertex(st, x, z)
            _horizon_vertex(st, x + step, z)
            _horizon_vertex(st, x, z + step)"""
        local = """_vertex(st, x, z)
            _vertex(st, x + step, z)
            _vertex(st, x, z + step)"""
        self.assertIn(macro, source)
        self.assertIn(local, source)

    def test_materials_keep_backface_culling_enabled(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertNotIn("CULL_DISABLED", source[source.index("func _material"):source.index("func _height")])


if __name__ == "__main__":
    unittest.main()
