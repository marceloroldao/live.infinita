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

ProposalLedger = load("proposal_ledger_world_tick_test", RUNTIME / "proposal_ledger.py").ProposalLedger
ConditionalPlanDispatcher = load("conditional_plan_dispatcher_world_tick_test", RUNTIME / "conditional_plan_dispatcher.py").ConditionalPlanDispatcher
ConditionalEventScheduler = load("conditional_event_scheduler_world_tick_test", RUNTIME / "conditional_event_scheduler.py").ConditionalEventScheduler
SimulationClock = load("simulation_clock_world_tick_plan_test", RUNTIME / "simulation_clock.py").SimulationClock
WorldTickRunner = load("world_tick_plan_test", RUNTIME / "world_tick.py").WorldTickRunner


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc_01",
    "authority": "entity_agent",
    "subject_entity_id": "npc_01",
}


class FakeEngine:
    def __init__(self):
        self.world = {"environment": {"period": "night"}, "state_hash": "h0", "entities": []}

    def load_world(self):
        return dict(self.world)


class FakeGuarded:
    def __init__(self):
        self.engine = FakeEngine()

    def commit(self, *args, **kwargs):
        raise AssertionError("conditional plan scheduling must not directly mutate world")


class FakePlanLedger:
    TERMINAL = frozenset({"completed", "failed", "cancelled"})

    def __init__(self):
        self.rows = []

    def active(self):
        return [dict(row) for row in self.rows if row.get("status") not in self.TERMINAL]


class FakePlanScheduler:
    def __init__(self):
        self.ledger = FakePlanLedger()
        self.tick_calls = []
        self._counter = 0

    def schedule(self, *, intent, principal, proposer_id, proposal_id=None, idempotency_key=None, priority=0):
        for row in self.ledger.rows:
            if idempotency_key and row.get("idempotency_key") == idempotency_key:
                return dict(row)
        self._counter += 1
        row = {
            "plan_id": f"plan_{self._counter}",
            "proposal_id": proposal_id,
            "intent": dict(intent),
            "principal": dict(principal),
            "proposer_id": proposer_id,
            "idempotency_key": idempotency_key,
            "priority": int(priority),
            "status": "planned",
            "next_step_index": 0,
        }
        self.ledger.rows.append(row)
        return dict(row)

    def tick(self, plan_id):
        self.tick_calls.append(plan_id)
        for row in self.ledger.rows:
            if row["plan_id"] == plan_id:
                row["status"] = "running"
                row["next_step_index"] = 1
                return dict(row)
        raise KeyError(plan_id)


class ConditionalPlanWorldTickTest(unittest.TestCase):
    def test_conditional_intent_plan_can_start_in_same_tick(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposals = ProposalLedger(tmp / "proposals.jsonl")
            plans = FakePlanScheduler()
            dispatcher = ConditionalPlanDispatcher(proposals, plans)
            conditions = ConditionalEventScheduler(
                tmp / "conditional.jsonl",
                FakeGuarded(),
                plan_dispatcher=dispatcher,
            )
            conditions.register(
                condition={"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                principal=PRINCIPAL,
                one_shot=True,
            )
            clock = SimulationClock(tmp / "clock.json", tick_duration_ms=500)
            runner = WorldTickRunner(clock, plans, conditional_event_scheduler=conditions)

            result = runner.tick()

            self.assertTrue(result["advanced"])
            self.assertEqual(result["clock"]["tick"], 1)
            self.assertEqual(len(result["conditional_events"]), 1)
            conditional = result["conditional_events"][0]
            self.assertEqual(conditional["effect_kind"], "plan_intent")
            self.assertIsNotNone(conditional["last_proposal_id"])
            self.assertIsNotNone(conditional["last_plan_id"])
            self.assertEqual(plans.tick_calls, [conditional["last_plan_id"]])
            self.assertEqual(result["plans"][0]["plan_id"], conditional["last_plan_id"])
            proposal = proposals.get(conditional["last_proposal_id"])
            self.assertEqual(proposal["status"], "approved")


if __name__ == "__main__":
    unittest.main()
