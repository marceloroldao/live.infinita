from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps" / "renderer-godot" / "warm_prefetch.gd"
SCENE = ROOT / "apps" / "renderer-godot" / "main.tscn"


class WarmPrefetchContractTest(unittest.TestCase):
    def test_prefetch_is_bounded_and_ephemeral(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("MAX_WARM_CACHE := 192", text)
        self.assertIn("MAX_AGE_MS := 12000", text)
        self.assertIn("warm_cache.erase(entity_id)", text)
        self.assertIn("_evict_expired()", text)

    def test_scene_attaches_prefetch_node(self) -> None:
        scene = SCENE.read_text(encoding="utf-8")
        self.assertIn('res://warm_prefetch.gd', scene)
        self.assertIn('name="WarmPrefetch"', scene)

    def test_prefetch_never_instantiates_entities(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("EntityVisual.new", text)
        self.assertNotIn("add_child", text)
        self.assertNotIn("load(", text)
        self.assertNotIn("preload(", text)


if __name__ == "__main__":
    unittest.main()
