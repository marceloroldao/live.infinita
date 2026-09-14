from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
AUDIENCE = ROOT / "apps" / "audience"
for value in (str(ROOT), str(RUNTIME), str(AUDIENCE)):
    if value not in sys.path:
        sys.path.insert(0, value)

from collective_intent import CollectiveIntentEngine
from collective_world import CollectiveWorldEvolver
from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from autonomous_runtime import region_catalog_from_world
from packages.spatial import DeterministicIntentPlanner, FileRegionColdStore


class CollectiveIntentTest(unittest.TestCase):
    def test_two_distinct_viewers_can_create_converged_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CollectiveIntentEngine(Path(tmpdir) / "state.json")
            engine.min_score = 1.5
            engine.min_contributors = 2
            engine.min_dominance = 0.55
            engine.cooldown_seconds = 0

            first = engine.ingest_comment(
                source="tiktok", actor_id="a", display_name="A",
                text="Quero explorar a floresta", now=100.0,
            )
            second = engine.ingest_comment(
                source="tiktok", actor_id="b", display_name="B",
                text="Vamos para a mata e as árvores", now=101.0,
            )
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            snapshot = engine.snapshot(now=102.0)
            self.assertEqual(snapshot["dominant"], "forest")
            self.assertEqual(snapshot["contributors"], 2)
            self.assertTrue(snapshot["ready"])

    def test_repeated_same_viewer_does_not_manufacture_consensus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CollectiveIntentEngine(Path(tmpdir) / "state.json")
            engine.min_score = 1.0
            engine.min_contributors = 2
            engine.cooldown_seconds = 0
            self.assertIsNotNone(engine.ingest_comment(
                source="tiktok", actor_id="solo", text="rio ponte agua", now=100.0,
            ))
            self.assertIsNone(engine.ingest_comment(
                source="tiktok", actor_id="solo", text="rio rio rio", now=105.0,
            ))
            snapshot = engine.snapshot(now=106.0)
            self.assertEqual(snapshot["contributors"], 1)
            self.assertFalse(snapshot["ready"])

    def test_telemetry_amplifies_but_never_chooses_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CollectiveIntentEngine(Path(tmpdir) / "state.json")
            engine.min_score = 0.1
            engine.min_contributors = 1
            engine.cooldown_seconds = 0
            for index in range(20):
                engine.ingest_telemetry({
                    "kind": "like",
                    "received_at_unix": 100.0 + index,
                    "metadata": {"count": 50},
                }, now=100.0 + index)
            snapshot = engine.snapshot(now=121.0)
            self.assertIsNone(snapshot["dominant"])
            self.assertFalse(snapshot["ready"])
            self.assertGreater(snapshot["engagement"], 0)

    def test_natural_question_can_express_village_intent(self) -> None:
        theme, weight, matches = CollectiveIntentEngine.classify_text(
            "Será que tem alguém morando por perto? Talvez exista uma vila."
        )
        self.assertEqual(theme, "village")
        self.assertGreaterEqual(weight, 1.0)
        self.assertTrue(any(term in matches for term in ("alguem morando", "vila")))

    def test_natural_question_can_express_forest_intent(self) -> None:
        theme, _weight, matches = CollectiveIntentEngine.classify_text(
            "O que existe depois da trilha na floresta, entre as árvores?"
        )
        self.assertEqual(theme, "forest")
        self.assertIn("floresta", matches)

    def test_general_question_stays_conversation_only(self) -> None:
        theme, weight, matches = CollectiveIntentEngine.classify_text(
            "Qual é a capital do Japão e quantas pessoas moram lá?"
        )
        self.assertIsNone(theme)
        self.assertEqual(weight, 0.0)
        self.assertEqual(matches, [])

    def test_scene_terms_match_words_not_accidental_substrings(self) -> None:
        theme, weight, matches = CollectiveIntentEngine.classify_text(
            "Estou curioso: a solução parece boa para o casamento."
        )
        self.assertIsNone(theme)
        self.assertEqual(weight, 0.0)
        self.assertEqual(matches, [])


class CollectiveWorldEvolutionTest(unittest.TestCase):
    def test_collective_chapter_grows_map_moves_nov_and_preserves_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bootstrap = ROOT / "examples" / "world-state.nov-live.bootstrap.json"
            store = FileRegionColdStore(root / "cold")
            engine = ColdAuthoritativeWorldEngine(bootstrap, root / "data", store)
            evolver = CollectiveWorldEvolver(store)
            guarded = GuardedMutationService(engine, decision_log_file=root / "data" / "decisions.jsonl")

            decision = {
                "dominant": "river",
                "dominant_score": 4.2,
                "dominance": 0.72,
                "contributors": 5,
                "scores": {"river": 4.2, "forest": 1.0, "village": 0.4, "field": 0.2},
                "chapter": 1,
                "decided_at_unix": 123.0,
            }
            planned = evolver.plan(engine.load_world(), decision)
            result = guarded.commit(
                planned["operations"],
                principal={
                    "source": "collective_intent",
                    "actor_id": "collective-audience",
                    "authority": "system",
                    "subject_entity_id": None,
                },
                narration=planned["narration"],
            )
            self.assertTrue(result["ok"])
            world = result["world"]
            region_id = planned["region_id"]
            landmark_id = planned["target_entity_id"]
            self.assertTrue(any(row.get("id") == region_id and row.get("biome") == "river" for row in world["regions"]))
            self.assertEqual(store.get_entity(landmark_id)["region_id"], region_id)
            self.assertEqual(store.get_entity("nov")["region_id"], region_id)
            self.assertEqual(world["story"]["chapter"], 1)
            self.assertEqual(world["story"]["motif"], "river")
            self.assertTrue(engine.verify_replay()["ok"])

            # Planner starts from bootstrap topology, then refreshes from the live
            # authoritative world and must understand the newly-created region.
            with bootstrap.open(encoding="utf-8") as fh:
                import json
                bootstrap_world = json.load(fh)
            planner = DeterministicIntentPlanner(store, region_catalog_from_world(bootstrap_world))
            planner.set_world_provider(engine.load_world)
            route_plan = planner.plan({
                "intent": "move_to_entity",
                "actor_entity_id": "nov",
                "target_entity_id": "ancient_tree",
            })
            self.assertEqual(route_plan.source_region_id, region_id)
            self.assertIn("clearing", route_plan.region_path)
            self.assertEqual(route_plan.goal_region_id, "deep_forest")


if __name__ == "__main__":
    unittest.main()
