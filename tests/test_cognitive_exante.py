from __future__ import annotations

from copy import deepcopy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cognitive_exante import build_exante_forecast, evaluate_exante_forecast  # noqa: E402
from cognitive_shadow import CognitiveShadowRecorder, summarize_shadow_file  # noqa: E402
from shadow_world_tick import ShadowWorldTickRunner  # noqa: E402


def frame():
    interventions = (
        SimpleNamespace(proposal_id="p-fire", action="nov_to_fire", target_entity_id="fire"),
        SimpleNamespace(proposal_id="p-shelter", action="nov_to_shelter", target_entity_id="shelter"),
    )
    candidates = (
        SimpleNamespace(proposal_id="p-fire", candidate_id="c-fire"),
        SimpleNamespace(proposal_id="p-shelter", candidate_id="c-shelter"),
    )
    return SimpleNamespace(frame_id="frame-1", available_interventions=interventions, candidate_outcomes=candidates)


def target(x, y, region="clearing"):
    return {"id": "target", "position": {"x": x, "y": y}, "region_id": region}


def observer(x=0, y=0):
    return {"id": "nov", "position": {"x": x, "y": y}, "region_id": "clearing"}


class ExanteForecastTests(unittest.TestCase):
    def build(self, **kwargs):
        args = dict(frame=frame(), observer=observer(), targets={"fire": target(10, 0), "shelter": target(30, 0)},
                    world_version=12, world_sequence=20)
        args.update(kwargs)
        return build_exante_forecast(**args)

    def evaluate(self, forecast, after, *, target_after=None, before=None):
        return evaluate_exante_forecast(
            forecast,
            observer_before=before or observer(),
            observer_after=after,
            target_after=target_after or target(10, 0),
        )

    def test_freeze_before_tick_and_hit(self):
        f = self.build()
        self.assertEqual(f["selection_phase"], "pre_tick")
        self.assertEqual(f["target_entity_id"], "fire")
        self.assertIsNone(f["candidate_id"])
        self.assertIsNone(f["action"])
        self.assertFalse(f["predicts_action"])
        self.assertEqual(f["issued_world_sequence"], 20)
        self.assertEqual(f["target_position"], {"x": 10.0, "y": 0.0})
        self.assertEqual(self.evaluate(f, observer(4, 0))["status"], "hit")
        self.assertEqual(self.evaluate(f, observer(-4, 0))["status"], "miss")
        self.assertEqual(f["distance_before"], 10.0)  # evaluation does not change issued forecast

    def test_stationary_and_target_changed_are_not_evaluable(self):
        f = self.build()
        stationary = self.evaluate(f, observer())
        self.assertEqual(stationary["status"], "not_evaluable")
        self.assertEqual(stationary["reason"], "observer_stationary")
        moved_target = self.evaluate(f, observer(4, 0), target_after=target(11, 0))
        self.assertEqual(moved_target["status"], "not_evaluable")
        self.assertEqual(moved_target["reason"], "target_changed")
        removed_target = evaluate_exante_forecast(f, observer_before=observer(), observer_after=observer(4, 0), target_after=None)
        self.assertEqual(removed_target["reason"], "target_missing")

    def test_equal_distance_and_already_at_target_abstain(self):
        tied = self.build(targets={"fire": target(10, 0), "shelter": target(-10, 0)})
        self.assertEqual(tied["status"], "abstained")
        self.assertEqual(tied["reason"], "distance_tie")
        current = self.build(observer=observer(10, 0))
        self.assertEqual(current["reason"], "already_at_target")
        self.assertEqual(self.evaluate(tied, observer(1, 0))["status"], "abstained")

    def test_unique_targets_and_determinism(self):
        original = frame()
        duplicate = SimpleNamespace(proposal_id="p-duplicate", action="nov_explore", target_entity_id="fire")
        original.available_interventions += (duplicate,)
        a = self.build(frame=original)
        b = self.build(frame=original)
        self.assertEqual(a, b)
        self.assertEqual(a["target_entity_id"], "fire")
        self.assertIsNotNone(a["forecast_id"])


class IntegrationTests(unittest.TestCase):
    def test_posthoc_choice_cannot_change_frozen_prediction(self):
        class Store:
            def __init__(self):
                self.rows = {
                    "nov": {"id": "nov", "type": "human", "region_id": "clearing",
                            "position": {"x": 0, "y": 0}, "properties": {"needs": {"safety": 0.8}}},
                    "fire_01": {"id": "fire_01", "region_id": "clearing", "position": {"x": 10, "y": 0}},
                    "shelter_marker": {"id": "shelter_marker", "region_id": "shelter", "position": {"x": 30, "y": 0}},
                    "ancient_tree": {"id": "ancient_tree", "region_id": "deep_forest", "position": {"x": 100, "y": 0}},
                }

            def get_entity(self, key):
                return deepcopy(self.rows.get(key))

        class Runner:
            def __init__(self, world, store):
                self.world, self.store, self.clock = world, store, object()

            def tick(self):
                self.world["sequence"] += 1
                self.world["version"] += 1
                self.store.rows["nov"]["region_id"] = "shelter"
                self.store.rows["nov"]["position"] = {"x": 30, "y": 0}
                return {"clock": {"tick": self.world["sequence"]},
                        "plans": [{"plan_id": "p", "actor_entity_id": "nov", "status": "completed"}],
                        "npc_needs": [], "events": [], "conditional_events": [], "npc_strategies": []}

        with tempfile.TemporaryDirectory() as td:
            world = {"world_id": "w", "sequence": 5, "version": 6,
                     "environment": {"period": "day", "weather": "clear", "biome": "forest"}}
            store = Store()
            path = Path(td) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(path, world_provider=lambda: deepcopy(world),
                                               store=store, enabled=True)
            token = recorder.begin_tick()
            self.assertEqual(token.exante_forecast["target_entity_id"], "fire_01")
            wrapper = ShadowWorldTickRunner(Runner(world, store), recorder)
            result = wrapper.tick()
            self.assertEqual(result["cognitive_shadow"]["status"], "recorded")
            row = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["best_candidate"]["action"], "nov_to_shelter")
            self.assertEqual(row["exante_forecast"]["target_entity_id"], "fire_01")
            self.assertEqual(row["exante_evaluation"]["status"], "miss")
            self.assertFalse(row["world_mutated_by_shadow"])
            self.assertFalse(row["predictive_accuracy_evaluable"])
            summary = summarize_shadow_file(path)
            self.assertEqual(summary["exante_evaluated"], 1)
            self.assertEqual(summary["exante_directional_misaligned"], 1)
            self.assertEqual(summary["exante_directional_alignment_rate"], 0.0)

    def test_old_jsonl_is_not_claimed_as_prediction(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shadow.jsonl"
            path.write_text(json.dumps({"best_candidate": {"exact_structural_match": True}}) + "\n")
            summary = summarize_shadow_file(path)
            self.assertEqual(summary["records"], 1)
            self.assertEqual(summary["exante_evaluated"], 0)
            self.assertIsNone(summary["exante_directional_alignment_rate"])


if __name__ == "__main__":
    unittest.main()
