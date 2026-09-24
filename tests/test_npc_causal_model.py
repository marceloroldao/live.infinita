import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_causal_model import NpcCausalModel


class NpcCausalModelTest(unittest.TestCase):
    def test_repeated_transition_reinforces_without_becoming_fact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model = NpcCausalModel(Path(tmpdir) / "causal.json", prior_strength=2.0)
            first = model.observe_environment_transition(
                observation_id="o1",
                logical_tick=12,
                before={"period": "day", "weather": "clear", "danger_level": 0.05},
                after={"period": "night", "weather": "clear", "danger_level": 0.35},
                source_events=[{"scheduled_event_id": "night"}],
            )
            self.assertEqual(first["status"], "provisional")
            self.assertEqual(first["support_count"], 1)
            self.assertEqual(first["counter_count"], 0)
            self.assertLess(first["confidence"], 1.0)

            second = model.observe_environment_transition(
                observation_id="o2",
                logical_tick=36,
                before={"period": "day", "weather": "clear", "danger_level": 0.05},
                after={"period": "night", "weather": "clear", "danger_level": 0.40},
            )
            self.assertEqual(second["support_count"], 2)
            self.assertGreater(second["confidence"], first["confidence"])
            self.assertEqual(second["status"], "provisional")

    def test_counterevidence_reduces_directional_confidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model = NpcCausalModel(Path(tmpdir) / "causal.json", prior_strength=1.0)
            supported = model.observe_environment_transition(
                observation_id="support",
                logical_tick=12,
                before={"period": "day", "danger_level": 0.1},
                after={"period": "night", "danger_level": 0.5},
            )
            counter = model.observe_environment_transition(
                observation_id="counter",
                logical_tick=36,
                before={"period": "day", "danger_level": 0.7},
                after={"period": "night", "danger_level": 0.2},
            )
            self.assertEqual(counter["support_count"], 1)
            self.assertEqual(counter["counter_count"], 1)
            self.assertLess(counter["confidence"], supported["confidence"])
            self.assertAlmostEqual(counter["mean_effect_delta"], -0.05)

    def test_same_observation_is_idempotent_and_persistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "causal.json"
            model = NpcCausalModel(path)
            first = model.observe_environment_transition(
                observation_id="same",
                logical_tick=24,
                before={"period": "night", "danger_level": 0.35},
                after={"period": "day", "danger_level": 0.05},
            )
            again = model.observe_environment_transition(
                observation_id="same",
                logical_tick=24,
                before={"period": "night", "danger_level": 0.35},
                after={"period": "day", "danger_level": 0.90},
            )
            self.assertEqual(again["count"], 1)
            self.assertAlmostEqual(again["mean_effect_delta"], first["mean_effect_delta"])

            reopened = NpcCausalModel(path)
            hypothesis = reopened.hypothesis(from_period="night", to_period="day", expected_direction="decrease")
            self.assertIsNotNone(hypothesis)
            self.assertEqual(hypothesis["count"], 1)
            self.assertEqual(hypothesis["last_observation_id"], "same")

    def test_no_period_transition_produces_no_hypothesis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model = NpcCausalModel(Path(tmpdir) / "causal.json")
            result = model.observe_environment_transition(
                observation_id="stable",
                logical_tick=7,
                before={"period": "day", "danger_level": 0.05},
                after={"period": "day", "danger_level": 0.20},
            )
            self.assertIsNone(result)
            self.assertEqual(model.hypotheses(), [])


if __name__ == "__main__":
    unittest.main()
