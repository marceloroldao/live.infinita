from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIENCE_DIR = ROOT / "apps" / "audience"
RUNTIME_DIR = ROOT / "apps" / "world-runtime"
for path in (AUDIENCE_DIR, RUNTIME_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from interaction_story import InteractionStoryContinuity  # noqa: E402
from story_narrator_v1 import StoryContinuityNarrator  # noqa: E402


class InteractionStoryContinuityTests(unittest.TestCase):
    def test_only_confirmed_world_mutation_becomes_persistent_story(self) -> None:
        planner = InteractionStoryContinuity(max_beats=4)
        comment = {
            "source": "tiktok",
            "source_event_id": "comment-1",
            "actor_id": "viewer-1",
            "text": "Nov vai para a fogueira",
        }
        self.assertIsNone(
            planner.plan(
                world={},
                comment=comment,
                interaction_result={"world_mutated": False},
                collective_state={},
                now=100.0,
            )
        )
        planned = planner.plan(
            world={},
            comment=comment,
            interaction_result={
                "world_mutated": True,
                "event": {"event_id": "world-1", "action": "nov_to_fire"},
            },
            collective_state={},
            now=101.0,
        )
        self.assertIsNotNone(planned)
        beat = planned["beat"]
        self.assertEqual(beat["action"], "nov_to_fire")
        self.assertEqual(beat["world_event_id"], "world-1")
        self.assertIn("fogueira", beat["consequence"].lower())
        self.assertNotIn("text", beat)
        self.assertNotIn("Nov vai para a fogueira", repr(planned["story"]))

    def test_story_beats_are_bounded_and_incremental(self) -> None:
        planner = InteractionStoryContinuity(max_beats=4)
        world = {}
        for index in range(7):
            planned = planner.plan(
                world=world,
                comment={"source": "simulator", "source_event_id": f"c{index}"},
                interaction_result={
                    "world_mutated": True,
                    "event": {"event_id": f"e{index}", "action": "nov_explore"},
                },
                collective_state={},
                now=100.0 + index,
            )
            world = {"story": planned["story"]}
        self.assertEqual(world["story"]["beat"], 7)
        self.assertEqual(len(world["story"]["beats"]), 4)
        self.assertEqual(world["story"]["beats"][0]["beat"], 4)
        self.assertEqual(world["story"]["beats"][-1]["beat"], 7)

    def test_continuity_narrator_reads_confirmed_story_and_fallback_tells_consequence(self) -> None:
        narrator = StoryContinuityNarrator(window_seconds=90)
        comment = narrator.observe_comment(
            source="simulator",
            actor_id="u1",
            display_name="Ana",
            text="Nov vai para a fogueira",
            source_event_id="c1",
            now=100,
        )
        world = {
            "world_id": "w",
            "sequence": 9,
            "environment": {"period": "night", "biome": "forest"},
            "story": {
                "chapter": 2,
                "title": "A noite na clareira",
                "beat": 1,
                "last_interaction": {
                    "beat": 1,
                    "action": "nov_to_fire",
                    "consequence": "Nov seguiu em direção à fogueira.",
                },
                "beats": [{"beat": 1, "action": "nov_to_fire", "consequence": "Nov seguiu em direção à fogueira."}],
            },
        }
        cue = narrator.render_interaction(
            config={},
            comment=comment,
            world=world,
            collective_state={},
            interaction_result={"world_mutated": True, "event": {"action": "nov_to_fire"}},
            now=100,
        )
        self.assertIn("fogueira", cue.text.lower())
        self.assertIn("história", cue.text.lower())
        context = narrator._world_context(world)
        self.assertEqual(context["story"]["beat"], 1)
        self.assertEqual(len(context["story"]["recent_confirmed_beats"]), 1)

    def test_collective_evolution_speaks_only_with_recent_human_interaction(self) -> None:
        narrator = StoryContinuityNarrator(window_seconds=90)
        world = {
            "world_id": "w",
            "sequence": 10,
            "environment": {"period": "day", "biome": "river"},
            "story": {"chapter": 3, "title": "A margem que ainda não existia", "motif": "river"},
        }
        silent = narrator.render_collective_evolution(
            config={},
            world=world,
            collective_state={"dominant": "river"},
            evolution={"theme": "river", "chapter": 3, "contributors": 2},
            now=100,
        )
        self.assertEqual(silent.mode, "silent")
        self.assertEqual(silent.text, "")

        narrator.observe_comment(
            source="tiktok", actor_id="u1", display_name="Ana", text="rio", now=101
        )
        narrator.observe_comment(
            source="tiktok", actor_id="u2", display_name="Beto", text="vamos ao rio", now=102
        )
        cue = narrator.render_collective_evolution(
            config={},
            world=world,
            collective_state={"dominant": "river", "contributors": 2},
            evolution={"theme": "river", "chapter": 3, "contributors": 2},
            now=102,
        )
        self.assertEqual(cue.mode, "collective")
        self.assertIn("rio", cue.text.lower())
        self.assertIn("história", cue.text.lower())

    def test_production_wrapper_and_collective_preservation_contract(self) -> None:
        unit = (ROOT / "deploy" / "live-infinita.service").read_text(encoding="utf-8")
        wrapper = (RUNTIME_DIR / "main_story_live.py").read_text(encoding="utf-8")
        runtime = (RUNTIME_DIR / "interaction_story_runtime.py").read_text(encoding="utf-8")
        collective = (RUNTIME_DIR / "collective_world.py").read_text(encoding="utf-8")
        self.assertIn("main_story_live:app", unit)
        self.assertIn("import interaction_story_runtime", wrapper)
        self.assertIn("main_live._original_gateway_payload = _story_aware_gateway", runtime)
        self.assertIn('story["beats"] = deepcopy(previous_story["beats"][-16:])', collective)


if __name__ == "__main__":
    unittest.main()
