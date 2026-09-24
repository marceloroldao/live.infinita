from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

ledger_module = load("plan_ledger_arbiter_test", RUNTIME / "plan_ledger.py")
arbiter_module = load("plan_arbiter_test_module", RUNTIME / "plan_arbiter.py")
PlanLedger = ledger_module.PlanLedger
PlanArbiter = arbiter_module.PlanArbiter


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc_01",
    "authority": "entity_agent",
    "subject_entity_id": "npc_01",
}


def make_plan(actor: str = "npc_01"):
    return {
        "intent_type": "move_to_position",
        "actor_entity_id": actor,
        "source_region_id": "r0",
        "goal_region_id": "r1",
        "region_path": ["r0", "r1"],
        "steps": [
            {
                "step_index": 0,
                "kind": "move",
                "intent": {"intent": "move_to_position", "actor_entity_id": actor, "position": {"x": 1, "y": 0}, "region_id": "r1"},
                "expected_region_id": "r0",
                "goal_region_id": "r1",
            },
            {
                "step_index": 1,
                "kind": "move",
                "intent": {"intent": "move_to_position", "actor_entity_id": actor, "position": {"x": 2, "y": 0}, "region_id": "r1"},
                "expected_region_id": "r1",
                "goal_region_id": "r1",
            },
        ],
    }


class PlanArbiterTest(unittest.TestCase):
    def create(self, ledger, *, key, priority, actor="npc_01"):
        return ledger.create(
            proposal_id=None,
            proposer_id="test",
            principal={**PRINCIPAL, "actor_id": actor, "subject_entity_id": actor},
            intent={"intent": "move_to_position", "actor_entity_id": actor},
            plan=make_plan(actor),
            idempotency_key=key,
            priority=priority,
            actor_entity_id=actor,
        )

    def test_higher_priority_preempts_same_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            normal = self.create(ledger, key="normal", priority=10)
            urgent = self.create(ledger, key="urgent", priority=100)
            arbiter = PlanArbiter(ledger)
            result = arbiter.reconcile()
            self.assertEqual([row["plan_id"] for row in result["runnable"]], [urgent["plan_id"]])
            parked = ledger.get(normal["plan_id"])
            self.assertEqual(parked["status"], "waiting")
            self.assertEqual(parked["waiting_reason"], "preempted")
            self.assertEqual(parked["preempted_by_plan_id"], urgent["plan_id"])
            self.assertEqual(len(result["preemptions"]), 1)

    def test_preempted_plan_resumes_same_cursor_after_urgent_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            normal = self.create(ledger, key="normal", priority=10)
            normal = ledger.transition(normal["plan_id"], "running", next_step_index=1)
            urgent = self.create(ledger, key="urgent", priority=100)
            arbiter = PlanArbiter(ledger)
            arbiter.reconcile()
            parked = ledger.get(normal["plan_id"])
            self.assertEqual(parked["next_step_index"], 1)

            urgent = ledger.get(urgent["plan_id"])
            if urgent["status"] == "planned":
                urgent = ledger.transition(urgent["plan_id"], "running")
            ledger.transition(urgent["plan_id"], "completed")

            result = arbiter.reconcile()
            resumed = ledger.get(normal["plan_id"])
            self.assertEqual(resumed["status"], "running")
            self.assertEqual(resumed["next_step_index"], 1)
            self.assertIsNone(resumed["preempted_by_plan_id"])
            self.assertEqual(result["resumptions"][0]["plan_id"], normal["plan_id"])

    def test_equal_priority_keeps_oldest_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            first = self.create(ledger, key="first", priority=50)
            second = self.create(ledger, key="second", priority=50)
            result = PlanArbiter(ledger).reconcile()
            self.assertEqual(result["runnable"][0]["plan_id"], first["plan_id"])
            self.assertEqual(ledger.get(second["plan_id"])["status"], "waiting")

    def test_different_actors_do_not_preempt_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            a = self.create(ledger, key="a", priority=1, actor="npc_a")
            b = self.create(ledger, key="b", priority=999, actor="npc_b")
            result = PlanArbiter(ledger).reconcile()
            self.assertEqual({row["plan_id"] for row in result["runnable"]}, {a["plan_id"], b["plan_id"]})
            self.assertEqual(result["preemptions"], [])

    def test_replanning_plan_does_not_block_runnable_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            blocked = self.create(ledger, key="blocked", priority=1000)
            blocked = ledger.transition(blocked["plan_id"], "running")
            ledger.transition(blocked["plan_id"], "replanning", last_error="route stale")
            normal = self.create(ledger, key="normal", priority=10)
            result = PlanArbiter(ledger).reconcile()
            self.assertEqual([row["plan_id"] for row in result["runnable"]], [normal["plan_id"]])
            self.assertEqual(result["blocked"][0]["plan_id"], blocked["plan_id"])


if __name__ == "__main__":
    unittest.main()
