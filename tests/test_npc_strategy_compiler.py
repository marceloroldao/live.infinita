import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "world-runtime"))

from npc_strategy_compiler import NpcStrategyCompileError, NpcStrategyCompiler


class NpcStrategyCompilerTest(unittest.TestCase):
    def setUp(self):
        self.compiler = NpcStrategyCompiler()

    def test_compiles_via_shelter_into_two_semantic_move_phases(self):
        plan = self.compiler.compile(
            actor_entity_id="npc",
            need="energy",
            target_entity_id="goal",
            context={"period": "night"},
            strategy={
                "strategy_id": "via_shelter:shelter",
                "expected_value": 0.42,
                "predicted_satisfaction": 0.8,
                "phases": [
                    {"kind": "move_to_entity", "target_entity_id": "shelter"},
                    {"kind": "move_to_entity", "target_entity_id": "goal"},
                ],
            },
        )
        self.assertEqual(plan["strategy_plan_schema"], "npc_strategy_plan_v1")
        self.assertEqual(len(plan["phases"]), 2)
        self.assertEqual(plan["phases"][0]["intent"]["target_entity_id"], "shelter")
        self.assertEqual(plan["phases"][1]["intent"]["target_entity_id"], "goal")
        self.assertEqual(plan["phases"][0]["intent"]["strategy_id"], "via_shelter:shelter")
        self.assertFalse(plan["phases"][0]["intent"]["need_outcome_eligible"])
        self.assertTrue(plan["phases"][1]["intent"]["need_outcome_eligible"])

    def test_compiles_wait_then_direct_without_mutation(self):
        plan = self.compiler.compile(
            actor_entity_id="npc",
            need="safety",
            target_entity_id="goal",
            strategy={
                "strategy_id": "wait_then_direct",
                "phases": [
                    {"kind": "wait_ticks", "ticks": 3},
                    {"kind": "move_to_entity", "target_entity_id": "goal"},
                ],
            },
        )
        self.assertEqual(plan["phases"][0]["intent"]["intent"], "wait_ticks")
        self.assertEqual(plan["phases"][0]["intent"]["ticks"], 3)
        self.assertFalse(plan["phases"][0]["intent"]["need_outcome_eligible"])
        self.assertTrue(plan["phases"][1]["intent"]["need_outcome_eligible"])

    def test_direct_terminal_move_is_outcome_eligible(self):
        plan = self.compiler.compile(
            actor_entity_id="npc",
            need="social",
            target_entity_id="goal",
            strategy={
                "strategy_id": "direct",
                "phases": [{"kind": "move_to_entity", "target_entity_id": "goal"}],
            },
        )
        self.assertTrue(plan["phases"][0]["intent"]["need_outcome_eligible"])

    def test_invalid_phase_fails_closed(self):
        with self.assertRaises(NpcStrategyCompileError):
            self.compiler.compile(
                actor_entity_id="npc",
                need="energy",
                target_entity_id="goal",
                strategy={"strategy_id": "bad", "phases": [{"kind": "teleport"}]},
            )


if __name__ == "__main__":
    unittest.main()
