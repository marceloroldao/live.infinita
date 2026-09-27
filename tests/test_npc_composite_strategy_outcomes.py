import tempfile
import json
import os
import unittest
from unittest.mock import patch
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

    def test_indexed_incremental_completions_learn_once_without_full_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            execution = {
                "strategy_execution_id": "sx-incremental",
                "status": "completed",
                "principal": {"actor_id": "npc"},
                "strategy_plan": {
                    "strategy_id": "direct", "actor_entity_id": "npc", "need": "energy",
                    "target_entity_id": "goal", "context": {},
                },
                "completed_phases": [
                    {"kind": "move_to_entity", "child_plan_id": "terminal", "completed_logical_tick": 9},
                ],
            }
            outcome = {
                "plan_id": "terminal", "status": "applied", "need": "energy",
                "target_entity_id": "goal", "outcome": {"before": 0.9, "after": 0.5},
            }
            class IndexedExecutions:
                def __init__(self):
                    self.calls = 0
                def unprocessed_completed(self, processed):
                    self.calls += 1
                    return [] if execution["strategy_execution_id"] in processed else [execution]
                def current(self):
                    raise AssertionError("full strategy copy")
            class IndexedNeedOutcomes:
                def get_applied(self, plan_id):
                    return outcome if plan_id == "terminal" else None
                def history(self):
                    raise AssertionError("full need-outcome replay")
            executor = IndexedExecutions()
            experience = NpcStrategyExperience(Path(tmpdir) / "experience.json", min_samples=1)
            audit = Path(tmpdir) / "audit.jsonl"
            plans = FakePlanLedger({"terminal": {
                "plan_id": "terminal", "started_logical_tick": 5, "completed_logical_tick": 9,
                "preemption_count": 0, "replan_count": 0,
            }})
            processor = NpcCompositeStrategyOutcomeProcessor(
                audit, executor, plans, IndexedNeedOutcomes(), experience
            )
            self.assertEqual(len(processor.process_completed()), 1)
            with patch.object(processor, "history", side_effect=AssertionError("full composite replay")):
                self.assertEqual(processor.process_completed(), [])
            rebooted = NpcCompositeStrategyOutcomeProcessor(
                audit, executor, plans, IndexedNeedOutcomes(), experience
            )
            self.assertEqual(rebooted.process_completed(), [])
            self.assertEqual(len(rebooted.history()), 1)
            self.assertEqual(executor.calls, 3)
            self.assertEqual(
                experience.strategy_stats("npc", "energy", "goal", "direct", {})["count"], 1
            )

    def test_composite_processed_index_invalidates_on_external_append_and_replace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            audit = Path(tmpdir) / "audit.jsonl"
            experience = NpcStrategyExperience(Path(tmpdir) / "experience.json")
            processor = NpcCompositeStrategyOutcomeProcessor(
                audit, FakeStrategyExecutor([]), FakePlanLedger({}),
                FakeNeedOutcomes([]), experience,
            )
            self.assertEqual(processor._processed(), set())
            with audit.open("ab") as fh:
                fh.write((json.dumps({"strategy_execution_id": "external"}) + "\n").encode("utf-8"))
            self.assertEqual(processor._processed(), {"external"})
            replacement = Path(tmpdir) / "replacement.jsonl"
            replacement.write_text(json.dumps({"strategy_execution_id": "new"}) + "\n", encoding="utf-8")
            os.replace(replacement, audit)
            self.assertEqual(processor._processed(), {"new"})
            processor._append({"strategy_execution_id": "local", "status": "applied"})
            with patch.object(processor, "history", side_effect=AssertionError("unexpected replay")):
                self.assertEqual(processor._processed(), {"new", "local"})



if __name__ == "__main__":
    unittest.main()
