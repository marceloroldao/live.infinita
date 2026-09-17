from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


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

    def test_default_music_volume_is_deliberately_low(self):
        self.assertLessEqual(AUDIO.RETRO_SCORE_VOLUME, 0.12)
        audio = AUDIO.RetroProgramAudio()
        audio.update_world(self.world(period="night"))
        status = audio.ambient_status()
        self.assertLess(status["retro_score"]["night_gain"], 1.0)

    def test_night_insects_are_soft_texture_not_high_pure_beep(self):
        audio = AUDIO.RetroProgramAudio()
        audio.cricket_next = 0
        samples = [audio._night_insects(True) for _ in range(12000)]
        energy = sum(abs(value) for value in samples)
        peak = max(abs(value) for value in samples)
        self.assertGreater(energy, 0.01)
        self.assertLess(peak, 0.01)
        status = audio.ambient_status()
        self.assertEqual(status["night_ambience"]["texture"], "soft-noise-chirp")
        self.assertFalse(status["night_ambience"]["pure_high_beep"])

    def test_production_unit_points_to_stable_retro_entry_point(self):
        unit = (ROOT / "deploy" / "live-infinita-audio.service").read_text(encoding="utf-8")
        stable = (ROOT / "apps" / "audio-service" / "stable_audio.py").read_text(encoding="utf-8")
        self.assertIn("apps/audio-service/stable_audio.py", unit)
        self.assertIn("LIVE_INFINITA_AUDIO_SAMPLE_RATE=16000", unit)
        self.assertIn("StableRetroProgramAudio", stable)
        self.assertIn("ambient_suspended_during_voice", stable)
        self.assertIn("audio_deadline_misses", stable)
        self.assertIn("wideband-16k-to-48k", stable)


class _FakeAudio:
    def __init__(self):
        self.world_updates = 0

    def update_world(self, _world):
        self.world_updates += 1
        return AUDIO.server_audio.WorldAudioState()

    def ambient_status(self):
        return {"ambient_enabled": True}


class InteractionNarrationAudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.audio = _FakeAudio()
        self.load_patch = patch.object(AUDIO.server_audio, "load_last_identity", return_value="")
        self.status_patch = patch.object(AUDIO.server_audio, "write_status")
        self.persist_patch = patch.object(AUDIO.server_audio, "persist_last_identity")
        self.load_patch.start()
        self.status_patch.start()
        self.persist = self.persist_patch.start()
        self.addCleanup(self.load_patch.stop)
        self.addCleanup(self.status_patch.stop)
        self.addCleanup(self.persist_patch.stop)
        self.service = AUDIO.InteractionNarrationService(self.audio)

    async def test_autonomous_world_narration_never_enters_tts_queue(self):
        world = self.world_with_legacy_narration("A noite caiu e Nov caminhou.")
        await self.service.submit_world(world)
        self.assertEqual(self.audio.world_updates, 1)
        self.assertTrue(self.service.queue.empty())

    async def test_interaction_cue_is_the_only_tts_trigger(self):
        await self.service.submit_narration_cue({
            "cue_id": "interaction:c1:1",
            "text": "Ana, Nov ouviu você. A trilha parece responder.",
            "mode": "individual",
            "participants": 1,
            "theme": "forest",
        })
        identity, text = self.service.queue.get_nowait()
        self.assertEqual(identity, "interaction:c1:1")
        self.assertIn("Ana", text)
        self.persist.assert_called_once_with("interaction:c1:1")

    @staticmethod
    def world_with_legacy_narration(text):
        return {
            "environment": {"biome": "forest", "period": "night", "weather": "clear"},
            "entities": [],
            "narration": {"text": text},
            "last_event": {"event_id": "auto-evt"},
        }


if __name__ == "__main__":
    unittest.main()
