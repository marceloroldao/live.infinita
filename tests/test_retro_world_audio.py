from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "apps" / "audio-service"
if str(AUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIO_DIR))

import retro_audio as AUDIO  # noqa: E402


class RetroWorldAudioTests(unittest.TestCase):
    @staticmethod
    def world(*, biome="forest", period="day"):
        return {
            "environment": {"biome": biome, "period": period, "weather": "clear"},
            "entities": [
                {
                    "id": "nov",
                    "type": "human",
                    "position": {"x": 640.0, "y": 360.0},
                    "properties": {"label": "Nov"},
                }
            ],
        }

    def test_status_exposes_retro_score_as_world_reactive_layer(self):
        audio = AUDIO.RetroProgramAudio()
        audio.update_world(self.world(biome="river"))
        status = audio.ambient_status()
        self.assertEqual(status["ambient_provider"], "local-procedural-retro-world-reactive")
        self.assertIn("retro-score", status["ambient_scene"]["layers"])
        self.assertEqual(status["ambient_scene"]["music_theme"], "flowing-waterway")
        self.assertEqual(status["ambient_scene"]["music_style"], "procedural-retro-game")
        self.assertFalse(status["retro_score"]["copyrighted_music"])

    def test_each_biome_has_a_distinct_music_identity(self):
        roots = set()
        labels = set()
        for biome in ("forest", "river", "village", "field"):
            profile = AUDIO.RetroProgramAudio.retro_profile(
                AUDIO.server_audio.WorldAudioState(biome=biome, period="day")
            )
            roots.add(profile["root_midi"])
            labels.add(profile["label"])
        self.assertEqual(len(roots), 4)
        self.assertEqual(len(labels), 4)

    def test_night_is_slower_and_one_octave_lower(self):
        day = AUDIO.RetroProgramAudio.retro_profile(
            AUDIO.server_audio.WorldAudioState(biome="forest", period="day")
        )
        night = AUDIO.RetroProgramAudio.retro_profile(
            AUDIO.server_audio.WorldAudioState(biome="forest", period="night")
        )
        self.assertLess(night["bpm"], day["bpm"])
        self.assertEqual(night["transpose"], -12)
        self.assertEqual(day["transpose"], 0)

    def test_score_generates_continuous_nonzero_pcm_without_clipping(self):
        audio = AUDIO.RetroProgramAudio()
        state = audio.update_world(self.world(biome="village"))
        energy = 0.0
        peaks = []
        for _ in range(6000):
            left, right = audio._retro_sample(state)
            energy += abs(left) + abs(right)
            peaks.extend((left, right))
        self.assertGreater(energy, 20.0)
        self.assertLessEqual(max(abs(value) for value in peaks), 2.0)

    def test_production_unit_points_to_retro_entry_point(self):
        unit = (ROOT / "deploy" / "live-infinita-audio.service").read_text(encoding="utf-8")
        self.assertIn("apps/audio-service/retro_audio.py", unit)


if __name__ == "__main__":
    unittest.main()
