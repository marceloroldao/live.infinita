from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIENCE_DIR = ROOT / "apps" / "audience"
if str(AUDIENCE_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIENCE_DIR))

from story_narrator import LiveStoryNarrator, NarrationSuppressed  # noqa: E402


class StoryNarratorTests(unittest.TestCase):
    @staticmethod
    def world():
        return {
            "world_id": "test-world",
            "sequence": 7,
            "environment": {"period": "night", "weather": "clear", "biome": "forest"},
            "story": {"chapter": 2, "motif": "river"},
        }

    @staticmethod
    def collective(theme="river", contributors=1):
        return {
            "dominant": theme,
            "dominance": 0.72,
            "contributors": contributors,
            "comment_signals": contributors,
            "chapter": 2,
            "ready": contributors >= 2,
        }

    def test_one_active_person_is_addressed_directly(self):
        narrator = LiveStoryNarrator(window_seconds=90)
        comment = narrator.observe_comment(
            source="tiktok", actor_id="u1", display_name="Ana", text="vamos ao rio", now=100
        )
        cue = narrator.render_interaction(
            config={}, comment=comment, world=self.world(), collective_state=self.collective(), now=100
        )
        self.assertEqual(cue.mode, "individual")
        self.assertEqual(cue.participants, 1)
        self.assertIn("Ana", cue.text)
        self.assertIn("rio", cue.text.lower())

    def test_multiple_people_become_collective_not_comment_by_comment(self):
        narrator = LiveStoryNarrator(window_seconds=90, collective_min_interval_seconds=8)
        narrator.observe_comment(
            source="tiktok", actor_id="u1", display_name="Ana", text="rio", now=100
        )
        second = narrator.observe_comment(
            source="tiktok", actor_id="u2", display_name="Beto", text="vamos ao rio", now=101
        )
        cue = narrator.render_interaction(
            config={}, comment=second, world=self.world(), collective_state=self.collective(contributors=2), now=101
        )
        self.assertEqual(cue.mode, "collective")
        self.assertEqual(cue.participants, 2)
        self.assertNotIn("Beto,", cue.text)

        third = narrator.observe_comment(
            source="tiktok", actor_id="u3", display_name="Caio", text="ponte", now=103
        )
        with self.assertRaises(NarrationSuppressed):
            narrator.render_interaction(
                config={}, comment=third, world=self.world(), collective_state=self.collective(contributors=3), now=103
            )

    def test_previous_narration_is_supplied_to_next_openai_phrase(self):
        requests = []
        outputs = iter([
            "Ana chama Nov para o rio. A trilha parece escutar. Talvez a margem responda.",
            "Ana insiste, e a margem volta ao centro da história. O caminho agora parece mais próximo.",
        ])

        def transport(payload, _api_key):
            requests.append(payload)
            return {"output_text": next(outputs)}

        narrator = LiveStoryNarrator(window_seconds=90, transport=transport)
        first = narrator.observe_comment(
            source="tiktok", actor_id="u1", display_name="Ana", text="rio", now=100
        )
        narrator.render_interaction(
            config={"openai_api_key": "test", "openai_model": "test-model"},
            comment=first,
            world=self.world(),
            collective_state=self.collective(),
            now=100,
        )
        second = narrator.observe_comment(
            source="tiktok", actor_id="u1", display_name="Ana", text="continua", now=110
        )
        narrator.render_interaction(
            config={"openai_api_key": "test", "openai_model": "test-model"},
            comment=second,
            world=self.world(),
            collective_state=self.collective(),
            now=110,
        )
        context_text = requests[1]["input"][1]["content"][0]["text"].split("\n", 1)[1]
        context = json.loads(context_text)
        self.assertEqual(len(context["story_history"]), 1)
        self.assertIn("Ana chama Nov", context["story_history"][0]["text"])
        self.assertEqual(len(narrator.story_snapshot()), 2)

    def test_collective_evolution_becomes_story_chapter_cue(self):
        narrator = LiveStoryNarrator()
        cue = narrator.render_collective_evolution(
            config={},
            world=self.world(),
            collective_state=self.collective(contributors=4),
            evolution={"theme": "river", "chapter": 3, "contributors": 4},
            now=200,
        )
        self.assertEqual(cue.mode, "collective_chapter")
        self.assertEqual(cue.participants, 4)
        self.assertIn("capítulo 3", cue.text.lower())


if __name__ == "__main__":
    unittest.main()
