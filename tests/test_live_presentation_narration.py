from pathlib import Path
import unittest

from packages.spatial.resolver import InterestConfig


ROOT = Path(__file__).resolve().parents[1]


class LivePresentationNarrationTests(unittest.TestCase):
    def test_showcase_hot_radius_keeps_clearing_visible_from_shelter(self) -> None:
        self.assertEqual(InterestConfig().hot_radius, 180.0)
        unit = (ROOT / "deploy" / "live-infinita.service").read_text(encoding="utf-8")
        self.assertIn('Environment="LIVE_INFINITA_HOT_RADIUS=280"', unit)

    def test_plan_scheduler_keeps_auditable_world_narration_separate(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "plan_scheduler.py").read_text(encoding="utf-8")
        self.assertNotIn('narration=f"plan {plan_id}', source)
        self.assertIn("_public_narration", source)

    def test_public_stream_is_silent_without_interaction_cue(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "main_live.py").read_text(encoding="utf-8")
        self.assertIn('"mode": "silent"', source)
        self.assertIn('"text": ""', source)
        self.assertIn("narration_cue", source)
        self.assertIn("_broadcast_story_cue", source)

    def test_audio_production_ignores_world_narration_and_speaks_only_cues(self) -> None:
        source = (ROOT / "apps" / "audio-service" / "retro_audio.py").read_text(encoding="utf-8")
        self.assertIn("class InteractionNarrationService", source)
        self.assertIn("async def submit_narration_cue", source)
        self.assertIn('narration_policy="interaction_only"', source)
        self.assertIn("await self.submit_narration_cue", source)
        world_method = source.split("async def submit_world", 1)[1].split("async def submit_narration_cue", 1)[0]
        self.assertNotIn("narration_from_world", world_method)
        self.assertNotIn("self.queue.put_nowait", world_method)


if __name__ == "__main__":
    unittest.main()
