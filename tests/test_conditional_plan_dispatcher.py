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

proposal_module = load("proposal_ledger_conditional_plan_test", RUNTIME / "proposal_ledger.py")
dispatch_module = load("conditional_plan_dispatcher_test", RUNTIME / "conditional_plan_dispatcher.py")
conditional_module = load("conditional_event_scheduler_plan_test", RUNTIME / "conditional_event_scheduler.py")
plan_scheduler_module = load("plan_scheduler_proposal_reconcile_test", RUNTIME / "plan_scheduler.py")
ProposalLedger = proposal_module.ProposalLedger
ConditionalPlanDispatcher = dispatch_module.ConditionalPlanDispatcher
ConditionalEventScheduler = conditional_module.ConditionalEventScheduler
PlanScheduler = plan_scheduler_module.PlanScheduler


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc_01",
    "authority": "entity_agent",
    "subject_entity_id": "npc_01",
}


class FakePlanScheduler:
    def __init__(self):
        self.calls = []

    def schedule(self, **kwargs):
        self.calls.append(kwargs)
        return {"plan_id": "plan_001", "proposal_id": kwargs.get("proposal_id"), "status": "planned"}


class FakeEngine:
    def __init__(self):
        self.world = {"environment": {"period": "night"}, "state_hash": "h0", "entities": []}
        self.commit_calls = 0

    def load_world(self):
        return dict(self.world)


class FakeGuarded:
    def __init__(self):
        self.engine = FakeEngine()

    def commit(self, *args, **kwargs):
        self.engine.commit_calls += 1
        raise AssertionError("plan intent trigger must not mutate world during scheduling")


class FakeCompletedPlanLedger:
    TERMINAL = frozenset({"completed", "failed", "cancelled"})

    def __init__(self, proposal_id):
        self.record = {
            "plan_id": "plan_done",
            "proposal_id": proposal_id,
            "status": "completed",
            "completed_steps": [{
                "step_index": 0,
                "mutation_decision_id": "md_001",
                "world_event_id": "evt_001",
                "state_hash": "h1",
            }],
        }

    def get(self, plan_id):
        return dict(self.record) if plan_id == "plan_done" else None


class ConditionalPlanDispatcherTest(unittest.TestCase):
    def test_dispatch_creates_approved_proposal_and_linked_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposals = ProposalLedger(Path(tmp) / "proposals.jsonl")
            plans = FakePlanScheduler()
            dispatcher = ConditionalPlanDispatcher(proposals, plans)
            result = dispatcher.dispatch(
                conditional_event_id="cev_1",
                tick=20,
                fire_index=1,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                principal=PRINCIPAL,
            )
            self.assertEqual(result["proposal"]["status"], "approved")
            self.assertEqual(result["proposal"]["origin"], "conditional_event")
            self.assertEqual(result["plan"]["proposal_id"], result["proposal"]["proposal_id"])
            self.assertEqual(len(plans.calls), 1)

            again = dispatcher.dispatch(
                conditional_event_id="cev_1",
                tick=20,
                fire_index=1,
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                principal=PRINCIPAL,
            )
            self.assertEqual(again["proposal"]["proposal_id"], result["proposal"]["proposal_id"])

    def test_conditional_plan_effect_schedules_without_world_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposals = ProposalLedger(Path(tmp) / "proposals.jsonl")
            plans = FakePlanScheduler()
            dispatcher = ConditionalPlanDispatcher(proposals, plans)
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(
                Path(tmp) / "conditional.jsonl",
                guarded,
                plan_dispatcher=dispatcher,
            )
            scheduler.register(
                condition={"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                principal=PRINCIPAL,
                one_shot=True,
            )
            row = scheduler.evaluate_tick(1)[0]
            self.assertEqual(row["status"], "completed")
            self.assertEqual(row["fire_count"], 1)
            self.assertEqual(row["last_plan_id"], "plan_001")
            self.assertIsNotNone(row["last_proposal_id"])
            self.assertEqual(guarded.engine.commit_calls, 0)

    def test_completed_plan_commits_approved_proposal_linkage(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposals = ProposalLedger(Path(tmp) / "proposals.jsonl")
            proposed = proposals.propose(
                origin="conditional_event",
                proposer_id="conditional:cev_1",
                proposal_kind="agent_intent",
                payload={"intent": {"intent": "move_to_position"}},
            )
            approved = proposals.approve(proposed["proposal_id"], decided_by="conditional_policy:cev_1")
            scheduler = PlanScheduler(
                FakeCompletedPlanLedger(approved["proposal_id"]),
                planner=object(),
                resolver=object(),
                guarded_mutations=object(),
                proposal_ledger=proposals,
            )
            result = scheduler.tick("plan_done")
            self.assertEqual(result["status"], "completed")
            final = proposals.get(approved["proposal_id"])
            self.assertEqual(final["status"], "committed")
            self.assertEqual(final["mutation_decision_id"], "md_001")
            self.assertEqual(final["world_event_id"], "evt_001")


if __name__ == "__main__":
    unittest.main()
