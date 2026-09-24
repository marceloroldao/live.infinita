import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_goal_sequence import NpcGoalSequence
from npc_horizon_strategy import NpcHorizonStrategy
from npc_need_horizon import NpcNeedHorizon


class FakeStore:
    def __init__(self):
        self.rows = {
            "nov": {
                "id": "nov",
                "properties": {
                    "safety_target_entity_id": "shelter",
                    "curiosity_target_entity_id": "tree",
                },
            }
        }

    def get_entity(self, entity_id):
        return self.rows.get(entity_id)


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()


class FakeBaseStrategy:
    def __init__(self):
        self.planner = FakePlanner()
        self.strategy_experience_provider = None
        self.counterfactual_provider = None

    def candidates(self, **kwargs):
        return []

    def rank(self, candidates, **kwargs):
        return [dict(row) for row in candidates]


class NpcHorizonGoalSequenceTest(unittest.TestCase):
    def test_defer_recommendation_is_attached_as_planning_metadata(self):
        overlay = NpcHorizonStrategy(
            FakeBaseStrategy(),
            NpcNeedHorizon(urgency_threshold=0.70, defer_margin=0.05),
            goal_sequence_provider=NpcGoalSequence(),
            future_need_weight=0.10,
        )
        rows = [{
            "strategy_id": "direct",
            "expected_value": 0.60,
            "effective_satisfaction": 0.30,
            "strategy_experience": None,
            "counterfactual": {
                "end_needs": {
                    "safety": 0.90,
                    "energy": 0.30,
                    "social": 0.20,
                    "curiosity": 0.80,
                }
            },
        }]
        chosen, ranked = overlay.choose(
            rows,
            need="curiosity",
            actor_entity_id="nov",
            target_entity_id="tree",
        )
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["need_horizon"]["defer_to_need"], "safety")
        sequence = chosen["goal_sequence"]
        self.assertEqual(sequence["mode"], "defer_current")
        self.assertEqual([goal["need"] for goal in sequence["goals"]], ["safety", "curiosity"])
        self.assertEqual(sequence["goals"][0]["target_entity_id"], "shelter")
        self.assertFalse(sequence["mutates_state"])
        self.assertEqual(ranked[0]["strategy_id"], "direct")


if __name__ == "__main__":
    unittest.main()
