import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_horizon_strategy import NpcHorizonStrategy
from npc_need_horizon import NpcNeedHorizon


class NpcNeedHorizonTest(unittest.TestCase):
    def test_detects_next_urgent_need_after_conditional_success(self):
        horizon = NpcNeedHorizon(urgency_threshold=0.70)
        result = horizon.assess(
            current_need="curiosity",
            predicted_satisfaction=0.35,
            counterfactual={
                "end_needs": {
                    "safety": 0.20,
                    "energy": 0.82,
                    "social": 0.30,
                    "curiosity": 0.90,
                }
            },
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["next_urgent_need"], "energy")
        self.assertEqual(result["recommended_need_sequence"], ["curiosity", "energy"])
        self.assertEqual(result["conditional_post_outcome_needs"]["curiosity"], 0.55)
        self.assertGreater(result["competing_need_pressure"], 0.0)
        self.assertFalse(result["mutates_state"])

    def test_can_recommend_deferring_lower_priority_need(self):
        horizon = NpcNeedHorizon(urgency_threshold=0.70, defer_margin=0.05)
        result = horizon.assess(
            current_need="curiosity",
            predicted_satisfaction=0.30,
            counterfactual={
                "end_needs": {
                    "safety": 0.85,
                    "energy": 0.60,
                    "social": 0.20,
                    "curiosity": 0.80,
                }
            },
        )
        self.assertEqual(result["defer_to_need"], "safety")


class FakeBaseStrategy:
    def candidates(self, **kwargs):
        return []

    def rank(self, candidates, **kwargs):
        return [dict(row) for row in candidates]


class NpcHorizonStrategyTest(unittest.TestCase):
    def test_overlay_penalizes_strategy_that_creates_future_urgency(self):
        overlay = NpcHorizonStrategy(FakeBaseStrategy(), NpcNeedHorizon(), future_need_weight=0.20)
        candidates = [
            {
                "strategy_id": "fast",
                "expected_value": 0.60,
                "effective_satisfaction": 0.30,
                "strategy_experience": None,
                "counterfactual": {
                    "end_needs": {"safety": 0.20, "energy": 0.60, "social": 0.20, "curiosity": 0.80}
                },
            },
            {
                "strategy_id": "slow",
                "expected_value": 0.62,
                "effective_satisfaction": 0.30,
                "strategy_experience": None,
                "counterfactual": {
                    "end_needs": {"safety": 0.20, "energy": 0.90, "social": 0.20, "curiosity": 0.80}
                },
            },
        ]
        chosen, ranked = overlay.choose(candidates, need="curiosity")
        by_id = {row["strategy_id"]: row for row in ranked}
        self.assertGreater(by_id["slow"]["future_need_penalty"], by_id["fast"]["future_need_penalty"])
        self.assertEqual(by_id["slow"]["need_horizon"]["next_urgent_need"], "energy")
        self.assertEqual(chosen["strategy_id"], "fast")

    def test_empirical_ready_strategy_is_not_changed_by_horizon_prior(self):
        overlay = NpcHorizonStrategy(FakeBaseStrategy(), NpcNeedHorizon(), future_need_weight=0.50)
        candidates = [{
            "strategy_id": "known",
            "expected_value": 0.50,
            "effective_satisfaction": 0.30,
            "strategy_experience": {"empirical_ready": True},
            "counterfactual": {
                "end_needs": {"safety": 0.95, "energy": 0.95, "social": 0.95, "curiosity": 0.95}
            },
        }]
        ranked = overlay.rank(candidates, need="curiosity")
        self.assertEqual(ranked[0]["future_need_penalty"], 0.0)
        self.assertIsNone(ranked[0]["need_horizon"])
        self.assertEqual(ranked[0]["expected_value"], 0.50)


if __name__ == "__main__":
    unittest.main()
