import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "world-runtime"))

from npc_strategy_executor import NpcStrategyExecutor


class FakeLedger:
    def __init__(self):
        self.rows = {}

    def get(self, plan_id):
        return self.rows.get(plan_id)


class FakePlanScheduler:
    def __init__(self):
        self.ledger = FakeLedger()
        self.calls = []

    def schedule(self, *, intent, principal, proposer_id, idempotency_key=None, priority=0, **kwargs):
        for plan_id, row in self.ledger.rows.items():
            if row.get("idempotency_key") == idempotency_key:
                return row
        plan_id = f"child_{len(self.ledger.rows) + 1}"
        row = {
            "plan_id": plan_id,
            "status": "planned",
            "intent": intent,
            "principal": principal,
            "proposer_id": proposer_id,
            "proposal_id": kwargs.get("proposal_id"),
            "priority": priority,
            "idempotency_key": idempotency_key,
        }
        self.ledger.rows[plan_id] = row
        self.calls.append(row)
        return row


class NpcStrategyExecutorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "strategy-executions.jsonl"
        self.scheduler = FakePlanScheduler()
        self.executor = NpcStrategyExecutor(self.path, self.scheduler)
        self.principal = {
            "source": "npc_need",
            "actor_id": "npc",
            "authority": "entity_agent",
            "subject_entity_id": "npc",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, phases):
        return {
            "strategy_plan_schema": "npc_strategy_plan_v1",
            "strategy_id": "strategy_x",
            "actor_entity_id": "npc",
            "need": "energy",
            "target_entity_id": "goal",
            "phases": phases,
        }

    def test_wait_ticks_uses_only_logical_ticks(self):
        execution = self.executor.start(
            self._plan([{
                "phase_index": 0,
                "kind": "wait_ticks",
                "intent": {"intent": "wait_ticks", "actor_entity_id": "npc", "ticks": 3},
            }]),
            principal=self.principal,
            proposer_id="npc:npc",
        )
        execution_id = execution["strategy_execution_id"]
        row = self.executor.tick(execution_id, logical_tick=10)
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["wait_started_tick"], 10)
        self.assertEqual(self.executor.tick(execution_id, logical_tick=12)["status"], "running")
        done = self.executor.tick(execution_id, logical_tick=13)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["completed_phases"][0]["wait_started_tick"], 10)

    def test_move_phase_creates_one_child_and_waits_for_completion(self):
        execution = self.executor.start(
            self._plan([{
                "phase_index": 0,
                "kind": "move_to_entity",
                "intent": {"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "goal"},
            }]),
            principal=self.principal,
            proposer_id="npc:npc",
            priority=700,
        )
        execution_id = execution["strategy_execution_id"]
        row = self.executor.tick(execution_id, logical_tick=1)
        self.assertEqual(len(self.scheduler.calls), 1)
        child_id = row["child_plan_id"]
        self.assertTrue(child_id)
        self.executor.tick(execution_id, logical_tick=2)
        self.assertEqual(len(self.scheduler.calls), 1)
        self.scheduler.ledger.rows[child_id]["status"] = "completed"
        done = self.executor.tick(execution_id, logical_tick=3)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["completed_phases"][0]["child_plan_id"], child_id)

    def test_restart_preserves_phase_cursor_and_child_plan(self):
        execution = self.executor.start(
            self._plan([
                {
                    "phase_index": 0,
                    "kind": "move_to_entity",
                    "intent": {"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "shelter"},
                },
                {
                    "phase_index": 1,
                    "kind": "move_to_entity",
                    "intent": {"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "goal"},
                },
            ]),
            principal=self.principal,
            proposer_id="npc:npc",
            idempotency_key="exec:1",
        )
        execution_id = execution["strategy_execution_id"]
        first = self.executor.tick(execution_id, logical_tick=1)
        first_child = first["child_plan_id"]
        self.scheduler.ledger.rows[first_child]["status"] = "completed"
        advanced = self.executor.tick(execution_id, logical_tick=2)
        self.assertEqual(advanced["phase_index"], 1)

        restarted = NpcStrategyExecutor(self.path, self.scheduler)
        current = restarted.get(execution_id)
        self.assertEqual(current["phase_index"], 1)
        self.assertIsNone(current["child_plan_id"])
        second = restarted.tick(execution_id, logical_tick=3)
        self.assertEqual(second["phase_index"], 1)
        self.assertNotEqual(second["child_plan_id"], first_child)
        self.assertEqual(len(self.scheduler.calls), 2)

    def test_proposal_is_attached_only_to_terminal_eligible_child(self):
        execution = self.executor.start(
            self._plan([
                {
                    "phase_index": 0,
                    "kind": "move_to_entity",
                    "intent": {
                        "intent": "move_to_entity", "actor_entity_id": "npc",
                        "target_entity_id": "shelter", "need": "energy",
                        "need_outcome_eligible": False,
                    },
                },
                {
                    "phase_index": 1,
                    "kind": "move_to_entity",
                    "intent": {
                        "intent": "move_to_entity", "actor_entity_id": "npc",
                        "target_entity_id": "goal", "need": "energy",
                        "need_outcome_eligible": True,
                    },
                },
            ]),
            principal=self.principal,
            proposer_id="npc:npc",
            proposal_id="proposal_1",
        )
        execution_id = execution["strategy_execution_id"]
        first = self.executor.tick(execution_id, logical_tick=1)
        first_child = first["child_plan_id"]
        self.assertIsNone(self.scheduler.ledger.rows[first_child]["proposal_id"])
        self.scheduler.ledger.rows[first_child]["status"] = "completed"
        self.executor.tick(execution_id, logical_tick=2)
        second = self.executor.tick(execution_id, logical_tick=3)
        second_child = second["child_plan_id"]
        self.assertEqual(self.scheduler.ledger.rows[second_child]["proposal_id"], "proposal_1")

    def test_child_failure_fails_strategy_without_advancing(self):
        execution = self.executor.start(
            self._plan([{
                "phase_index": 0,
                "kind": "move_to_entity",
                "intent": {"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "goal"},
            }]),
            principal=self.principal,
            proposer_id="npc:npc",
        )
        execution_id = execution["strategy_execution_id"]
        row = self.executor.tick(execution_id, logical_tick=1)
        self.scheduler.ledger.rows[row["child_plan_id"]]["status"] = "failed"
        failed = self.executor.tick(execution_id, logical_tick=2)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["phase_index"], 0)


if __name__ == "__main__":
    unittest.main()
