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
            # Story metadata may still exist authoritatively, but the conversational
            # host must not receive it as material for narration.
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
        self.assertNotIn("estou aqui para", cue.text.lower())
        self.assertNotIn("ouvi sua pergunta", cue.text.lower())

    def test_channel_account_name_is_not_spoken_as_a_viewer_name(self):
        narrator = LiveStoryNarrator(window_seconds=90)
        comment = narrator.observe_comment(
            source="tiktok",
            actor_id="self",
            display_name="Live Infinita",
            text="oi pessoal",
            now=100,
        )
        cue = narrator.render_interaction(
            config={},
            comment=comment,
            world=self.world(),
            collective_state=self.collective(theme=None, contributors=0),
            now=100,
        )
        self.assertFalse(cue.text.lower().startswith("live infinita"))
        self.assertTrue(any(term in cue.text.lower() for term in ("opa", "e aí", "fala")))

    def test_local_fallback_varies_instead_of_repeating_one_canned_sentence(self):
        narrator = LiveStoryNarrator(window_seconds=90)
        outputs = []
        for index in range(3):
            narrator.comments.clear()
            comment = narrator.observe_comment(
                source="tiktok",
                actor_id=f"u{index}",
                display_name=f"Pessoa {index}",
                text="isso é interessante",
                now=100 + index,
            )
            cue = narrator.render_interaction(
                config={},
                comment=comment,
                world=self.world(),
                collective_state=self.collective(theme=None, contributors=0),
                now=100 + index,
            )
            outputs.append(cue.text)
        self.assertEqual(len(set(outputs)), 3)

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

    def test_openai_can_answer_general_question_without_story_context(self):
        requests = []

        def transport(payload, _api_key):
            requests.append(payload)
            return {"output_text": "Tóquio. E é uma cidade gigantesca — mais de 14 milhões na área administrativa."}

        narrator = LiveStoryNarrator(window_seconds=90, transport=transport)
        comment = narrator.observe_comment(
            source="tiktok",
            actor_id="u1",
            display_name="Ana",
            text="qual a capital do Japão?",
            now=100,
        )
        cue = narrator.render_interaction(
            config={"openai_api_key": "test", "openai_model": "test-model"},
            comment=comment,
            world=self.world(),
            collective_state=self.collective(theme=None, contributors=0),
            now=100,
        )
        self.assertEqual(cue.mode, "individual")
        self.assertIn("Tóquio", cue.text)
        self.assertEqual(cue.generated_by, "openai:test-model")
        self.assertEqual(narrator.last_generation_source, "openai:test-model")
        self.assertIsNone(narrator.last_generation_error)
        self.assertEqual(len(requests), 1)

        system_prompt = requests[0]["input"][0]["content"][0]["text"]
        self.assertIn("apresentador humano de live", system_prompt)
        self.assertIn("Responda primeiro ao conteúdo concreto", system_prompt)
        self.assertIn("Não comece respostas dizendo 'Live Infinita'", system_prompt)
        self.assertIn("Não diga 'ouvi sua pergunta'", system_prompt)
        context_text = requests[0]["input"][1]["content"][0]["text"].split("\n", 1)[1]
        context = json.loads(context_text)
        self.assertNotIn("story_history", context)
        self.assertNotIn("story", context["world"])

    def test_model_failure_uses_natural_fallback_and_records_diagnostic(self):
        def transport(_payload, _api_key):
            raise RuntimeError("simulated outage")

        narrator = LiveStoryNarrator(window_seconds=90, transport=transport)
        comment = narrator.observe_comment(
            source="tiktok", actor_id="u1", display_name="Ana", text="oi", now=100
        )
        cue = narrator.render_interaction(
            config={"openai_api_key": "test", "openai_model": "test-model"},
            comment=comment,
            world=self.world(),
            collective_state=self.collective(theme=None, contributors=0),
            now=100,
        )
        self.assertEqual(cue.generated_by, "fallback")
        self.assertIsNotNone(narrator.last_generation_error)
        self.assertIn("simulated outage", narrator.last_generation_error)
        self.assertNotIn("estou aqui para", cue.text.lower())

    def test_collective_world_evolution_itself_is_silent(self):
        narrator = LiveStoryNarrator()
        cue = narrator.render_collective_evolution(
            config={"openai_api_key": "unused", "openai_model": "unused"},
            world=self.world(),
            collective_state=self.collective(contributors=4),
            evolution={"theme": "river", "chapter": 3, "contributors": 4},
            now=200,
        )
        self.assertEqual(cue.mode, "silent")
        self.assertEqual(cue.text, "")
        self.assertEqual(cue.generated_by, "suppressed")

    def test_host_keeps_no_narration_history(self):
        narrator = LiveStoryNarrator()
        self.assertFalse(hasattr(narrator, "history"))
        self.assertFalse(hasattr(narrator, "story_snapshot"))


if __name__ == "__main__":
    unittest.main()
