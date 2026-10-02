from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "apps" / "renderer-godot" / "world_map_features.gd"


class StaticFeatureBatching008AHTests(unittest.TestCase):
    def test_repeat_boxes_uses_multimesh(self) -> None:
        source = FEATURES.read_text(encoding="utf-8")
        section = source[source.index("func _repeat_boxes"):source.index("func _solid_box")]
        self.assertIn("MultiMesh.new()", section)
        self.assertIn("MultiMeshInstance3D.new()", section)
        self.assertIn("multimesh.instance_count = centers.size()", section)
        self.assertIn("set_instance_transform", section)

    def test_bridge_batches_repeated_visuals(self) -> None:
        source = FEATURES.read_text(encoding="utf-8")
        section = source[source.index("func _bridge"):source.index("func _house")]
        self.assertIn('"BridgePlanks"', section)
        self.assertIn('"BridgePosts"', section)
        self.assertIn("range(15)", section)
        self.assertIn("range(5)", section)
        self.assertNotIn('"BridgePlank_%d"', section)
        self.assertNotIn('_box(tile, "BridgePost"', section)
        self.assertIn('_solid_box(tile, "BridgeRail"', section)

    def test_stone_circle_is_batched(self) -> None:
        source = FEATURES.read_text(encoding="utf-8")
        start = source.index("func _special_landmark")
        special = source[start:]
        section = special[special.index('        "stone_circle":'):special.index('        "cave":')]
        self.assertIn('"StandingStones"', section)
        self.assertIn("range(8)", section)
        self.assertNotIn('"StandingStone_%d"', section)


if __name__ == "__main__":
    unittest.main()
