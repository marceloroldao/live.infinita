from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class TileCache008AFTests(unittest.TestCase):
    def test_cache_is_bounded_and_hidden(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        self.assertIn("const MAX_CACHED_TILES := 24", source)
        self.assertIn(' _tile_cache_root.name = "TileCache"'.strip(), source)
        self.assertIn("_tile_cache_root.visible = false", source)
        self.assertIn("func _prune_tile_cache() -> void:", source)
        self.assertIn("while _tile_cache_order.size() > MAX_CACHED_TILES:", source)

    def test_sync_reuses_cache_before_rebuilding(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        sync = source[source.index("func _sync_tiles"):source.index("func _on_world_slice")]
        self.assertIn("var cached_tile := _take_cached_tile(id)", sync)
        self.assertIn("_cache_tile(id, stale)", sync)
        self.assertLess(sync.index("_take_cached_tile(id)"), sync.index("var tile := Node3D.new()"))

    def test_projection_change_invalidates_cached_geometry(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        rebuild = source[source.index("func _rebuild_active_tiles"):source.index("func _decor_indices_for_tile")]
        self.assertIn("_clear_tile_cache()", rebuild)
        self.assertIn("stale.queue_free()", rebuild)


if __name__ == "__main__":
    unittest.main()
