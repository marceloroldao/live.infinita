from __future__ import annotations

from copy import deepcopy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cognitive_exante import build_exante_forecast, evaluate_exante_forecast  # noqa: E402
from cognitive_shadow import CognitiveShadowRecorder, summarize_shadow_file  # noqa: E402
from memoria_v2_adapter import build_nov_cognitive_frame  # noqa: E402
from shadow_world_tick import ShadowWorldTickRunner  # noqa: E402


def sample():
    world = {
        "world_id": "mvp012-test", "version": 10, "sequence": 20,
        "environment": {"period": "day", "danger_level": 0.35},
    }
    entities = {
        "nov": {
            "id": "nov", "type": "human", "region_id": "clearing",
            "position": {"x": 640, "y": 360},
            "properties": {"needs": {
                "safety": 0.2, "energy": 0.6, "social": 0.1, "curiosity": 0.8,
            }},
        },
        "fire_01": {"id": "fire_01", "region_id": "clearing", "position": {"x": 700, "y": 405}},
        "shelter_marker": {"id": "shelter_marker", "region_id": "shelter", "position": {"x": 900, "y": 375}},
        "ancient_tree": {"id": "ancient_tree", "region_id": "deep_forest", "position": {"x": 320, "y": 335}},
    }
    return world, entities


class Store:
    def __init__(self, entities):
        self.entities = entities

    def get_entity(self, key):
        row = self.entities.get(key)
        return deepcopy(row) if row is not None else None


class MovingRunner:
    def __init__(self, world, store, *, destination=None, shift_target=False):
        self.world, self.store, self.destination = world, store, destination
        self.shift_target = shift_target
        self.clock = object()

    def tick(self):
        self.world["version"] += 1
        self.world["sequence"] += 1
        if self.destination:
            self.store.entities["nov"]["position"] = dict(self.destination)
            if self.destination == {"x": 900, "y": 375}:
                self.store.entities["nov"]["region_id"] = "shelter"
        if self.shift_target:
            self.store.entities["fire_01"]["position"]["x"] += 1
        return {
            "clock": {"tick": self.world["sequence"]},
            "events": [{"id": "tick"}],
            "plans": [], "npc_needs": [], "npc_strategies": [], "conditional_events": [],
        }


class ExAnteTests(unittest.TestCase):
    def _record(self, *, destination=None, shift_target=False, change=None):
        world, entities = sample()
        if change:
            change(world, entities)
        store = Store(entities)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.jsonl"
            runner = MovingRunner(world, store, destination=destination, shift_target=shift_target)
            observer = deepcopy(entities["nov"])
            before = deepcopy(world)
            result = ShadowWorldTickRunner(
                runner, CognitiveShadowRecorder(
                    path, world_provider=lambda: deepcopy(world), store=store, enabled=True,
                ),
            ).tick()
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            return before, observer, world, result, rows[0], summarize_shadow_file(path)

    def test_forecast_frozen_before_tick_can_disagree_with_posthoc_match(self):
        before, observer, world, result, row, metrics = self._record(
            destination={"x": 900, "y": 375},
        )
        prediction = row["exante_forecast"]
        evaluated = row["exante_evaluation"]
        self.assertEqual(prediction["selection_phase"], "pre_tick")
        self.assertEqual(prediction["issued_world_sequence"], before["sequence"])
        self.assertEqual(prediction["target_entity_id"], "fire_01")
        self.assertFalse(prediction["predicts_action"])
        self.assertEqual(row["best_candidate"]["target_entity_id"], "shelter_marker")
        self.assertTrue(row["best_candidate"]["exact_structural_match"])
        self.assertEqual(evaluated["status"], "miss")
        self.assertIs(evaluated["hit"], False)
        self.assertFalse(row["world_mutated_by_shadow"])
        self.assertEqual(world["sequence"], before["sequence"] + 1)
        self.assertEqual(metrics["exante_forecasts"], 1)
        self.assertEqual(metrics["exante_evaluated"], 1)
        self.assertEqual(metrics["exante_directional_misaligned"], 1)

    def test_progress_is_a_hit_and_projection_is_not_a_satisfaction_claim(self):
        *_, row, metrics = self._record(destination={"x": 700, "y": 405})
        self.assertEqual(row["exante_evaluation"]["status"], "hit")
        self.assertEqual(metrics["exante_directional_aligned"], 1)
        projected = row["exante_forecast"]["projected_need_pressure"]
        self.assertIsNotNone(projected)
        self.assertEqual(projected["source"], "existing_npc_counterfactual_simulator")
        self.assertFalse(projected["mutates_world"])
        self.assertFalse(row["exante_forecast"]["need_projection_evaluable"])

    def test_stationary_or_lateral_motion_not_counted_as_miss(self):
        *_, stationary, metrics = self._record()
        self.assertEqual(stationary["exante_evaluation"]["status"], "not_evaluable")
        self.assertEqual(stationary["exante_evaluation"]["reason"], "observer_stationary")
        self.assertEqual(metrics["exante_abstained"], 1)
        self.assertIsNone(metrics["exante_directional_alignment_rate"])
        # A point on the same radius around the fire has zero net progress.
        *_, lateral, metrics = self._record(destination={"x": 655, "y": 465})
        self.assertEqual(lateral["exante_evaluation"]["reason"], "lateral_or_indeterminate_movement")
        self.assertEqual(metrics["exante_evaluated"], 0)

    def test_moving_target_is_not_evaluable(self):
        *_, row, metrics = self._record(
            destination={"x": 700, "y": 405}, shift_target=True,
        )
        self.assertEqual(row["exante_evaluation"]["reason"], "target_changed")
        self.assertEqual(metrics["exante_evaluated"], 0)

    def test_tied_target_abstains_and_does_not_fake_action_prediction(self):
        def tie(world, entities):
            entities["shelter_marker"]["position"] = {"x": 700, "y": 405}
        *_, row, metrics = self._record(
            destination={"x": 700, "y": 405}, change=tie,
        )
        self.assertEqual(row["exante_forecast"]["status"], "abstained")
        self.assertEqual(row["exante_forecast"]["reason"], "distance_tie")
        self.assertIsNone(row["exante_forecast"]["action"])
        self.assertEqual(row["exante_evaluation"]["status"], "abstained")
        self.assertEqual(metrics["exante_abstained"], 1)

    def test_no_risk_observation_does_not_invent_need_projection(self):
        def no_risk(world, entities):
            world["environment"].pop("danger_level")
        *_, row, _ = self._record(change=no_risk)
        self.assertIsNone(row["exante_forecast"]["projected_need_pressure"])

    def test_legacy_rows_do_not_enter_exante_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.jsonl"
            path.write_text(json.dumps({"best_candidate": {"exact_structural_match": True}}) + "\n")
            metrics = summarize_shadow_file(path)
            self.assertEqual(metrics["records"], 1)
            self.assertEqual(metrics["exante_evaluated"], 0)
            self.assertIsNone(metrics["exante_directional_alignment_rate"])


if __name__ == "__main__":
    unittest.main()
