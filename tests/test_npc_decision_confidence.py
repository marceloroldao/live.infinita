import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_confidence_strategy import NpcConfidenceStrategy
from npc_decision_confidence import NpcDecisionConfidence


class FakeBaseStrategy:
    def rank(self, candidates, **kwargs):
        return [dict(row) for row in candidates]

    def candidates(self, **kwargs):
        return []


class NpcDecisionConfidenceTest(unittest.TestCase):
    def test_heuristic_only_is_low_confidence(self):
        confidence = NpcDecisionConfidence()
        result = confidence.assess({"strategy_id": "direct"})
        self.assertEqual(result["level"], "low")
        self.assertAlmostEqual(result["score"], 0.20)
        self.assertFalse(result["empirical_dominant"])
        self.assertFalse(result["mutates_state"])

    def test_counterfactual_and_causal_support_raise_confidence(self):
        confidence = NpcDecisionConfidence()
        result = confidence.assess({
            "strategy_id": "via_shelter:shelter",
            "counterfactual": {"counterfactual_schema": "npc_counterfactual_v2"},
            "causal_forecast": {"confidence": 0.80},
            "need_horizon": {"competing_need_pressure": 0.50},
        })
        self.assertEqual(result["level"], "medium")
        self.assertGreater(result["score"], 0.60)
        sources = {row["source"] for row in result["sources"]}
        self.assertIn("counterfactual", sources)
        self.assertIn("causal_forecast", sources)
        self.assertIn("need_horizon", sources)

    def test_mature_empirical_experience_is_high_and_dominant(self):
        confidence = NpcDecisionConfidence()
        result = confidence.assess({
            "strategy_experience": {"empirical_ready": True, "count": 4},
            "counterfactual": {"counterfactual_schema": "npc_counterfactual_v2"},
            "causal_forecast": {"confidence": 1.0},
        })
        self.assertEqual(result["level"], "high")
        self.assertTrue(result["empirical_dominant"])
        self.assertGreaterEqual(result["score"], 0.80)
        self.assertEqual([row["source"] for row in result["sources"]], ["empirical_strategy"])

    def test_confidence_wrapper_does_not_reorder_strategies(self):
        wrapper = NpcConfidenceStrategy(FakeBaseStrategy(), NpcDecisionConfidence())
        candidates = [
            {"strategy_id": "a", "expected_value": 0.8},
            {"strategy_id": "b", "expected_value": 0.7, "counterfactual": {"x": 1}},
        ]
        ranked = wrapper.rank(candidates)
        self.assertEqual([row["strategy_id"] for row in ranked], ["a", "b"])
        self.assertIn("decision_confidence", ranked[0])
        self.assertIn("decision_confidence", ranked[1])


if __name__ == "__main__":
    unittest.main()
