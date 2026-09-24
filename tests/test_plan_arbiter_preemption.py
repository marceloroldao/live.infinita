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

ledger_module = load("plan_ledger_preemption_test", RUNTIME / "plan_ledger.py")
arbiter_module = load("plan_arbiter_preemption_test", RUNTIME / "plan_arbiter.py")
PlanLedger = ledger_module.PlanLedger
PlanArbiter = arbiter_module.PlanArbiter


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc_01",
    "authority": "entity_agent",
    "subject_entity_id": "npc_01",
}


def make_plan(intent_type: str, actor: str) -> dict:
    return {
        "intent_type": intent_type,
        "actor_entity_id": actor,
        "source_region_id": "r0",
        "goal_region_id": "r1",
        "region_path": ["r0", "r1"],
        "steps": [
            {
                "step_index": 0,
                "kind": "move",
                "intent": {
                    "intent": "move_to_position",
                    "actor_entity_id": actor,
                    "position": {"x": 10, "y": 0},
                    "region_id": "r1",
                },
                "expected_region_id": "r0",
                "goal_region_id": "r1",
            },
            {
                "step_index": 1,
                "kind": "move",
                "intent": {
                    "intent": "move_to_position",
                    "actor_entity_id": actor,
                    "position": {"x": 20, "y": 0},
                    "region_id": "r1",
                },
                "expected_region_id": "r1",
                "goal_region_id": "r1",
            },
        ],
    }


class PlanArbiterPreemptionTest(unittest.TestCase):
    def test_high_priority_plan_preempts_and_old_plan_resumes_with_cursor_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            normal = ledger.create(
                proposal_id=None,
                proposer_id="story",
                principal=PRINCIPAL,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                plan=make_plan("move_to_entity", "npc_01"),
                priority=10,
                actor_entity_id="npc_01",
            )
            normal = ledger.transition(normal["plan_id"], "running", next_step_index=1)

            urgent = ledger.create(
                proposal_id=None,
                proposer_id="hazard",
                principal=PRINCIPAL,
                intent={"intent": "move_to_position", "actor_entity_id": "npc_01", "position": {"x": -50, "y": 0}, "region_id": "safe"},
                plan=make_plan("move_to_position", "npc_01"),
                priority=100,
                actor_entity_id="npc_01",
            )

            arbiter = PlanArbiter(ledger)
            first = arbiter.reconcile()
            self.assertEqual([row["plan_id"] for row in first["runnable"]], [urgent["plan_id"]])
            suspended = ledger.get(normal["plan_id"])
            self.assertEqual(suspended["status"], "waiting")
            self.assertEqual(suspended["waiting_reason"], "preempted")
            self.assertEqual(suspended["preempted_by_plan_id"], urgent["plan_id"])
            self.assertEqual(suspended["next_step_index"], 1)

            urgent_running = ledger.transition(urgent["plan_id"], "running")
            ledger.transition(urgent_running["plan_id"], "completed")

            second = arbiter.reconcile()
            self.assertEqual([row["plan_id"] for row in second["runnable"]], [normal["plan_id"]])
            resumed = ledger.get(normal["plan_id"])
            self.assertEqual(resumed["status"], "running")
            self.assertIsNone(resumed["waiting_reason"])
            self.assertIsNone(resumed["preempted_by_plan_id"])
            self.assertEqual(resumed["next_step_index"], 1)

    def test_equal_priority_uses_creation_order_then_plan_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            first = ledger.create(
                proposal_id=None,
                proposer_id="a",
                principal=PRINCIPAL,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                plan=make_plan("move_to_entity", "npc_01"),
                priority=50,
                actor_entity_id="npc_01",
            )
            second = ledger.create(
                proposal_id=None,
                proposer_id="b",
                principal=PRINCIPAL,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "tree"},
                plan=make_plan("move_to_entity", "npc_01"),
                priority=50,
                actor_entity_id="npc_01",
            )
            arbiter = PlanArbiter(ledger)
            result = arbiter.reconcile()
            self.assertEqual(result["runnable"][0]["plan_id"], first["plan_id"])
            self.assertEqual(ledger.get(second["plan_id"])["status"], "waiting")

    def test_different_actors_can_run_concurrently(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PlanLedger(Path(tmp) / "plans.jsonl")
            p1 = ledger.create(
                proposal_id=None,
                proposer_id="x",
                principal=PRINCIPAL,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                plan=make_plan("move_to_entity", "npc_01"),
                priority=10,
                actor_entity_id="npc_01",
            )
            p2_principal = dict(PRINCIPAL)
            p2_principal["actor_id"] = "npc_02"
            p2_principal["subject_entity_id"] = "npc_02"
            p2 = ledger.create(
                proposal_id=None,
                proposer_id="y",
                principal=p2_principal,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_02", "target_entity_id": "nov"},
                plan=make_plan("move_to_entity", "npc_02"),
                priority=10,
                actor_entity_id="npc_02",
            )
            result = PlanArbiter(ledger).reconcile()
            self.assertEqual({row["plan_id"] for row in result["runnable"]}, {p1["plan_id"], p2["plan_id"]})


if __name__ == "__main__":
    unittest.main()
