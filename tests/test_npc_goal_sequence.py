import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_goal_sequence import NpcGoalSequence


class NpcGoalSequenceTest(unittest.TestCase):
    def setUp(self):
        self.planner = NpcGoalSequence()
        self.npc = {
            "id": "nov",
            "properties": {
                "safety_target_entity_id": "shelter",
                "rest_target_entity_id": "bed",
                "curiosity_target_entity_id": "tree",
            },
        }

    def test_defer_to_safety_places_safety_before_curiosity(self):
        result = self.planner.build(
            npc_entity=self.npc,
            current_need="curiosity",
            current_target_entity_id="tree",
            horizon={"defer_to_need": "safety", "next_urgent_need": "safety"},
        )
        self.assertEqual(result["mode"], "defer_current")
        self.assertEqual([row["need"] for row in result["goals"]], ["safety", "curiosity"])
        self.assertEqual(result["goals"][0]["target_entity_id"], "shelter")
        self.assertFalse(result["mutates_state"])

    def test_follow_up_energy_is_appended_after_current_goal(self):
        result = self.planner.build(
            npc_entity=self.npc,
            current_need="curiosity",
            current_target_entity_id="tree",
            horizon={"next_urgent_need": "energy", "defer_to_need": None},
        )
        self.assertEqual(result["mode"], "current_then_follow_up")
        self.assertEqual([row["need"] for row in result["goals"]], ["curiosity", "energy"])
        self.assertEqual(result["goals"][1]["target_entity_id"], "bed")

    def test_missing_prerequisite_target_fails_closed_to_current_goal(self):
        result = self.planner.build(
            npc_entity={"id": "nov", "properties": {"curiosity_target_entity_id": "tree"}},
            current_need="curiosity",
            current_target_entity_id="tree",
            horizon={"defer_to_need": "safety", "next_urgent_need": "safety"},
        )
        self.assertEqual(result["mode"], "defer_target_missing")
        self.assertEqual([row["need"] for row in result["goals"]], ["curiosity"])


if __name__ == "__main__":
    unittest.main()
