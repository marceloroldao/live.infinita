from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps" / "renderer-godot" / "interest_client.gd"
SCENE = ROOT / "apps" / "renderer-godot" / "main.tscn"


class InterestClientContractTest(unittest.TestCase):
    def test_interest_client_is_attached_to_scene(self) -> None:
        scene = SCENE.read_text(encoding="utf-8")
        self.assertIn('res://interest_client.gd', scene)
        self.assertIn('[node name="InterestClient" type="Node" parent="."]', scene)

    def test_interest_update_tracks_entity_not_absolute_snapshot(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"type": "interest_update"', script)
        self.assertIn('"observer_entity_id": observer_entity_id', script)
        self.assertNotIn('"position": {"x": last_position.x', script)

    def test_direction_is_derived_from_observer_motion(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('displacement.normalized()', script)
        self.assertIn('"direction": {"x": last_direction.x, "y": last_direction.y}', script)

    def test_updates_are_rate_limited(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('UPDATE_INTERVAL_MS', script)
        self.assertIn('POSITION_EPSILON', script)


if __name__ == "__main__":
    unittest.main()
