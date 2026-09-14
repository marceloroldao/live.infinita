from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "audio-service" / "server_audio.py"
SPEC = importlib.util.spec_from_file_location("live_infinita_server_audio", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIO
SPEC.loader.exec_module(AUDIO)


class WorldReactiveAudioTests(unittest.TestCase):
    @staticmethod
    def world(*, period="day", weather="clear", nov_x=640.0, nov_y=360.0, fire_lit=False):
        return {
            "environment": {"biome": "forest", "period": period, "weather": weather},
            "entities": [
                {
                    "id": "nov",
                    "type": "human",
                    "position": {"x": nov_x, "y": nov_y},
                    "properties": {"label": "Nov"},
                },
                {
                    "id": "fire_01",
                    "type": "campfire",
                    "position": {"x": 700.0, "y": 405.0},
                    "properties": {"lit": fire_lit},
                },
            ],
        }

    def test_day_forest_has_wind_forest_and_birds(self):
        audio = AUDIO.ProgramAudio()
        state = audio.update_world(self.world())
        self.assertEqual(state.period, "day")
        self.assertIn("wind", state.layers())
        self.assertIn("forest", state.layers())
        self.assertIn("day-birds", state.layers())
        self.assertNotIn("night-insects", state.layers())

    def test_night_replaces_birds_with_insects(self):
        audio = AUDIO.ProgramAudio()
        state = audio.update_world(self.world(period="night"))
        self.assertIn("night-insects", state.layers())
        self.assertNotIn("day-birds", state.layers())

    def test_lit_fire_is_spatial_and_exposed_as_layer(self):
        audio = AUDIO.ProgramAudio()
        state = audio.update_world(self.world(fire_lit=True))
        self.assertTrue(state.fire_lit)
        self.assertIn("campfire", state.layers())
        self.assertIsNotNone(state.fire_distance)
        assert state.fire_distance is not None
        self.assertTrue(math.isclose(state.fire_distance, 75.0, abs_tol=0.1))

    def test_position_change_activates_footsteps(self):
        audio = AUDIO.ProgramAudio()
        first = audio.update_world(self.world(nov_x=640.0))
        self.assertFalse(first.walking)
        moved = audio.update_world(self.world(nov_x=702.0))
        self.assertTrue(moved.walking)
        self.assertGreaterEqual(moved.walk_duration, 0.9)
        self.assertIn("footsteps", moved.layers())
        self.assertTrue(audio.ambient_status()["ambient_scene"]["walking"])

    def test_rain_is_derived_from_world_weather(self):
        audio = AUDIO.ProgramAudio()
        state = audio.update_world(self.world(weather="rain"))
        self.assertIn("rain", state.layers())

    def test_status_declares_local_world_reactive_provider(self):
        audio = AUDIO.ProgramAudio()
        audio.update_world(self.world(period="night", fire_lit=True))
        status = audio.ambient_status()
        self.assertEqual(status["ambient_provider"], "local-procedural-world-reactive")
        self.assertTrue(status["ambient_enabled"])
        self.assertIn("campfire", status["ambient_scene"]["layers"])
        self.assertIn("night-insects", status["ambient_scene"]["layers"])


if __name__ == "__main__":
    unittest.main()
