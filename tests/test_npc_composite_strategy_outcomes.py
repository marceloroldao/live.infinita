import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_composite_strategy_outcomes import NpcCompositeStrategyOutcomeProcessor
from npc_strategy_experience import NpcStrategyExperience


class FakeStrategyExecutor:
    def __init__(self, rows):
        self.rows = rows

    def current(self):
        return list(self.rows)


class FakePlanLedger:
    def __init__(self, rows):
        self.rows = rows

    def get(self, plan_id):
        return self.rows.get(plan_id)


class FakeNeedOutcomes:
    def __init__(self, rows):
        self.rows = rows

    def history(self):
        return list(self.rows)


class NpcCompositeStrategyOutcomeProcessorTest(unittest.TestCase):
    def test_completed_strategy_learns_once_from_terminal_need_outcome(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            execution = {
                "strategy_execution_id": "sx1",
                "status": "completed",
                "principal": {"actor_id": "npc"},
                "strategy_plan": {
                    "strategy_id": "via_shelter:shelter",
                    "actor_entity_id": "npc",
                    "need": "energy",
                    "target_entity_id": "goal",
                    "context": {"period": "night", "weather": "storm", "region_id": "r0", "danger_level": 0.8},
                },
                "completed_phases": [
                    {"phase_index": 0, "kind": "move_to_entity", "child_plan_id": "p1", "completed_logical_tick": 3},
                    {"phase_index": 1, "kind": "move_to_entity", "child_plan_id": "p2", "completed_logical_tick": 7},
                ],
            }
            plans = FakePlanLedger({
                "p1": {"plan_id": "p1", "started_logical_tick": 1, "completed_logical_tick": 3, "preemption_count": 1, "replan_count": 0},
                "p2": {"plan_id": "p2", "started_logical_tick": 4, "completed_logical_tick": 7, "preemption_count": 0, "replan_count": 1},
            })
            outcomes = FakeNeedOutcomes([{
                "plan_id": "p2",
                "status": "applied",
                "need": "energy",
                "target_entity_id": "goal",
                "outcome": {"before": 0.9, "after": 0.5},
            }])
            experience = NpcStrategyExperience(Path(tmpdir) / "experience.json", min_samples=1)
            processor = NpcCompositeStrategyOutcomeProcessor(
                Path(tmpdir) / "audit.jsonl",
                FakeStrategyExecutor([execution]),
                plans,
                outcomes,
                experience,
            )

            first = processor.process_completed()
            second = processor.process_completed()
            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])
            self.assertAlmostEqual(first[0]["satisfaction"], 0.4)
            self.assertEqual(first[0]["elapsed_ticks"], 7)
            self.assertEqual(first[0]["preemptions"], 1)
            self.assertEqual(first[0]["replans"], 1)

            stats = experience.strategy_stats(
                "npc", "energy", "goal", "via_shelter:shelter",
                {"period": "night", "weather": "storm", "region_id": "r0", "danger_level": 0.8},
            )
            self.assertIsNotNone(stats)
            self.assertEqual(stats["count"], 1)
            self.assertTrue(stats["empirical_ready"])
            self.assertAlmostEqual(stats["mean_satisfaction"], 0.4)
            self.assertAlmostEqual(stats["mean_elapsed_ticks"], 7.0)

    def test_incomplete_or_missing_terminal_outcome_does_not_learn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experience = NpcStrategyExperience(Path(tmpdir) / "experience.json", min_samples=1)
            execution = {
                "strategy_execution_id": "sx2",
                "status": "completed",
                "strategy_plan": {
                    "strategy_id": "direct",
                    "actor_entity_id": "npc",
                    "need": "energy",
                    "target_entity_id": "goal",
                    "context": {},
                },
                "completed_phases": [
                    {"kind": "move_to_entity", "child_plan_id": "p1", "completed_logical_tick": 2},
                ],
            }
            processor = NpcCompositeStrategyOutcomeProcessor(
                Path(tmpdir) / "audit.jsonl",
                FakeStrategyExecutor([execution]),
                FakePlanLedger({"p1": {"plan_id": "p1", "started_logical_tick": 1, "completed_logical_tick": 2}}),
                FakeNeedOutcomes([]),
                experience,
            )
            self.assertEqual(processor.process_completed(), [])
            self.assertIsNone(experience.strategy_stats("npc", "energy", "goal", "direct", {}))


if __name__ == "__main__":
    unittest.main()
