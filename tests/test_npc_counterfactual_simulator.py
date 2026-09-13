import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_counterfactual_simulator import NpcCounterfactualSimulator


class FakeForecast:
    def assess(self, *, context, estimated_ticks):
        tick = int(context.get("logical_tick", 0))
        period = str(context.get("period") or "day")
        danger = float(context.get("danger_level", 0.1))
        if period == "day" and tick < 12 <= tick + int(estimated_ticks):
            return {
                "to_period": "night",
                "projected_danger": 0.7,
                "current_danger": danger,
                "confidence": 0.8,
                "blend": 0.28,
            }
        return None


class NpcCounterfactualSimulatorTest(unittest.TestCase):
    def setUp(self):
        self.sim = NpcCounterfactualSimulator(FakeForecast())
        self.context = {"logical_tick": 10, "period": "day", "danger_level": 0.1}

    def test_direct_projection_crosses_night_without_mutation(self):
        strategy = {
            "strategy_id": "direct",
            "phases": [{"kind": "move_to_entity", "target_entity_id": "goal", "estimated_ticks": 3}],
        }
        original = dict(self.context)
        result = self.sim.simulate(strategy=strategy, context=self.context)
        self.assertFalse(result["mutates_world"])
        self.assertEqual(self.context, original)
        self.assertEqual(result["start_tick"], 10)
        self.assertEqual(result["end_tick"], 13)
        self.assertEqual(result["end_period"], "night")
        self.assertGreater(result["mean_effective_risk"], 0.1)
        self.assertEqual(len(result["trace"]), 1)

    def test_via_shelter_has_lower_projected_effective_risk(self):
        direct = {
            "strategy_id": "direct",
            "phases": [{"kind": "move_to_entity", "target_entity_id": "goal", "estimated_ticks": 3}],
        }
        sheltered = {
            "strategy_id": "via_shelter:shelter",
            "phases": [
                {"kind": "move_to_entity", "target_entity_id": "shelter", "estimated_ticks": 2},
                {"kind": "move_to_entity", "target_entity_id": "goal", "estimated_ticks": 1},
            ],
        }
        direct_result = self.sim.simulate(strategy=direct, context=self.context)
        shelter_result = self.sim.simulate(strategy=sheltered, context=self.context)
        self.assertLess(shelter_result["mean_effective_risk"], direct_result["mean_effective_risk"])
        self.assertEqual(len(shelter_result["trace"]), 2)
        self.assertGreater(shelter_result["trace"][0]["protection"], 0.0)

    def test_no_transition_keeps_current_period_and_risk(self):
        result = self.sim.simulate(
            strategy={"strategy_id": "direct", "phases": [{"kind": "move_to_entity", "estimated_ticks": 1}]},
            context={"logical_tick": 5, "period": "day", "danger_level": 0.2},
        )
        self.assertEqual(result["end_period"], "day")
        self.assertAlmostEqual(result["mean_effective_risk"], 0.2)


if __name__ == "__main__":
    unittest.main()
