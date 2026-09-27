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

from cognitive_contextual import freeze_contextual_forecast, stationary_evidence  # noqa: E402
from cognitive_shadow import CognitiveShadowRecorder, summarize_shadow_file  # noqa: E402
from shadow_world_tick import ShadowWorldTickRunner  # noqa: E402
from tests.test_memoria_v2_shadow_mode import FakeStore, FakeRunner  # noqa: E402


class Experience:
    def stats(self, npc_id, need, target_id, context):
        return {"count": 4, "empirical_ready": True, "mean_elapsed_ticks": 2.5, "last_plan_id": "prior-plan"}


class ContextualTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.store.entities["nov"]["properties"]["safety_target_entity_id"] = "shelter_marker"
        self.store.entities["nov"]["properties"]["rest_target_entity_id"] = "bed_nov"
        self.store.entities["bed_nov"] = {
            "id": "bed_nov", "region_id": "shelter", "position": {"x": 910, "y": 375},
        }
        self.needs = {"safety": 0.9, "energy": 0.3, "social": 0.1, "curiosity": 0.2}

    def freeze(self, needs=None):
        return freeze_contextual_forecast(
            frame_id="frame-before", world_version=10, world_sequence=20,
            observer=self.store.get_entity("nov"),
            needs=needs or self.needs,
            target_provider=self.store.get_entity,
            environment={"period": "day", "weather": "clear", "danger_level": 0.05},
            experience_provider=Experience(),
            need_source="npc_need_dynamics",
        )

    def test_contextual_uses_dynamic_need_and_configured_target_with_provenance(self):
        f, target = self.freeze()
        self.assertEqual(f["status"], "issued")
        self.assertEqual(f["selection_phase"], "pre_tick")
        self.assertFalse(f["predicts_action"])
        self.assertIsNone(f["action"])
        self.assertEqual(f["selected_need"], "safety")
        self.assertEqual(f["target_entity_id"], "shelter_marker")
        self.assertEqual(f["experience"]["sample_count"], 4)
        self.assertFalse(f["experience"]["used_to_rank"])
        self.assertEqual(f["need_source"], "npc_need_dynamics")
        self.assertEqual(target["region_id"], "shelter")
        self.assertEqual(f, self.freeze()[0])

    def test_no_target_and_ambiguous_target_abstain(self):
        social = {"safety": 0.2, "energy": 0.3, "social": 1.0, "curiosity": 0.1}
        f, target = self.freeze(social)
        self.assertEqual(f["status"], "abstained")
        self.assertEqual(f["reason"], "no_configured_target")
        self.assertIsNone(target)
        self.store.entities["nov"]["properties"]["safety_target_entity_ids"] = ["shelter_marker", "bed_nov"]
        f, target = self.freeze()
        self.assertEqual(f["reason"], "multiple_targets_without_ranked_evidence")
        self.assertIsNone(target)

    def test_missing_dynamic_values_abstain_instead_of_inventing(self):
        f, _ = self.freeze({"safety": 0.9})
        self.assertEqual(f["reason"], "need_state_unavailable")

    def test_stationary_evidence_is_not_a_causal_diagnosis(self):
        s = stationary_evidence(
            movement_distance=0,
            tick_result={"npc_needs": [{"npc_id": "nov", "status": "no_target"}],
                         "plans": [], "npc_strategies": []},
            contextual_forecast={"reason": "no_configured_target"},
        )
        self.assertTrue(s["stationary"])
        self.assertEqual(s["evidence_label"], "need_no_target_observed")
        self.assertFalse(s["causal_explanation_evaluable"])
        other = stationary_evidence(
            movement_distance=5, tick_result={"npc_needs": []}, contextual_forecast={},
        )
        self.assertFalse(other["stationary"])
        self.assertIsNone(other["evidence_label"])


class DynamicIntegrationTests(unittest.TestCase):
    def _world(self):
        return {
            "world_id": "w", "version": 10, "sequence": 20,
            "environment": {"period": "day", "weather": "clear", "danger_level": 0.05},
        }

    def test_dynamic_need_snapshots_and_paired_baselines(self):
        store = FakeStore()
        store.entities["nov"]["properties"]["safety_target_entity_id"] = "shelter_marker"
        needs = {"safety": 0.9, "energy": 0.3, "social": 0.1, "curiosity": 0.2}
        world = self._world()
        class Runner(FakeRunner):
            def tick(self):
                result = super().tick()
                needs["safety"] = 0.4
                result["npc_needs"] = [{"npc_id": "nov", "status": "scheduled"}]
                return result

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(
                path, world_provider=lambda: deepcopy(world),
                store=store, enabled=True,
                needs_provider=lambda npc: deepcopy(needs),
                experience_provider=Experience(),
            )
            result = ShadowWorldTickRunner(Runner(world, store), recorder).tick()
            self.assertEqual(result["cognitive_shadow"]["status"], "recorded")
            row = json.loads(path.read_text().strip())
            trajectory = row["trajectory_observation"]
            self.assertEqual(trajectory["need_levels_source_before"], "npc_need_dynamics")
            self.assertEqual(trajectory["need_levels_source_after"], "npc_need_dynamics")
            self.assertEqual(trajectory["need_levels_before"]["safety"], 0.9)
            self.assertEqual(trajectory["need_levels_after"]["safety"], 0.4)
            self.assertAlmostEqual(trajectory["need_level_deltas"]["safety"], -0.5)
            self.assertEqual(store.entities["nov"]["properties"]["needs"]["safety"], 0.2)
            self.assertEqual(row["exante_forecast"]["target_entity_id"], "fire_01")
            self.assertEqual(row["exante_evaluation"]["status"], "miss")
            self.assertEqual(row["contextual_forecast"]["target_entity_id"], "shelter_marker")
            self.assertEqual(row["contextual_evaluation"]["status"], "hit")
            self.assertFalse(row["world_mutated_by_shadow"])
            summary = summarize_shadow_file(path)
            self.assertEqual(summary["need_source_dynamic_records"], 1)
            self.assertEqual(summary["contextual_evaluated"], 1)
            self.assertEqual(summary["contextual_hits"], 1)
            self.assertEqual(summary["paired_evaluated"], 1)
            self.assertEqual(summary["paired_baseline_hits"], 0)
            self.assertEqual(summary["paired_contextual_hits"], 1)

    def test_stationary_no_target_does_not_count_as_prediction_error(self):
        store = FakeStore()
        world = self._world()
        needs = {"safety": 0.2, "energy": 0.3, "social": 1.0, "curiosity": 0.1}
        class Runner:
            def __init__(self):
                self.clock = object()
            def tick(self):
                return {
                    "clock": {"tick": 21}, "plans": [],
                    "events": [{"event_id": "e"}],
                    "npc_needs": [{"npc_id": "nov", "status": "no_target"}],
                    "npc_strategies": [], "conditional_events": [],
                }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(
                path, world_provider=lambda: deepcopy(world), store=store,
                needs_provider=lambda _: dict(needs), enabled=True,
            )
            result = ShadowWorldTickRunner(Runner(), recorder).tick()
            self.assertEqual(result["cognitive_shadow"]["status"], "recorded")
            row = json.loads(path.read_text().strip())
            self.assertEqual(row["contextual_forecast"]["reason"], "no_configured_target")
            self.assertEqual(row["contextual_evaluation"]["status"], "abstained")
            self.assertEqual(row["stationary_observation"]["evidence_label"], "need_no_target_observed")
            summary = summarize_shadow_file(path)
            self.assertEqual(summary["contextual_evaluated"], 0)
            self.assertIsNone(summary["contextual_hit_rate"])
            self.assertEqual(summary["stationary_records"], 1)
            self.assertEqual(summary["contextual_abstention_reasons"]["no_configured_target"], 1)

    def test_bootstrap_need_source_is_explicit_for_legacy_fakes(self):
        store = FakeStore()
        world = self._world()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(
                path, world_provider=lambda: deepcopy(world),
                store=store, enabled=True,
            )
            ShadowWorldTickRunner(FakeRunner(world, store), recorder).tick()
            row = json.loads(path.read_text().strip())
            self.assertEqual(row["trajectory_observation"]["need_levels_source_before"], "entity_properties_bootstrap")
            self.assertEqual(row["contextual_forecast"]["need_source"], "entity_properties_bootstrap")


if __name__ == "__main__":
    unittest.main()
