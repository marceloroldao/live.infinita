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

proposal_module = load("proposal_ledger_sustained_test", RUNTIME / "proposal_ledger.py")
dispatch_module = load("conditional_plan_dispatcher_sustained_test", RUNTIME / "conditional_plan_dispatcher.py")
conditional_module = load("conditional_event_scheduler_sustained_plan_test", RUNTIME / "conditional_event_scheduler.py")
ProposalLedger = proposal_module.ProposalLedger
ConditionalPlanDispatcher = dispatch_module.ConditionalPlanDispatcher
ConditionalEventScheduler = conditional_module.ConditionalEventScheduler


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc_01",
    "authority": "entity_agent",
    "subject_entity_id": "npc_01",
}


class FakeStore:
    def __init__(self):
        self.entities = {
            "nov": {"id": "nov", "region_id": "forest", "position": {"x": 0, "y": 0}},
            "npc_01": {"id": "npc_01", "region_id": "village", "position": {"x": 10, "y": 0}},
        }

    def get_entity(self, entity_id):
        value = self.entities.get(entity_id)
        return dict(value) if value else None

    def load_region(self, region_id):
        return [dict(v) for v in self.entities.values() if v.get("region_id") == region_id]


class FakeEngine:
    def __init__(self):
        self.cold_store = FakeStore()
        self.world = {"state_hash": "h0", "entities": []}

    def load_world(self):
        return dict(self.world)


class FakeGuarded:
    def __init__(self):
        self.engine = FakeEngine()
        self.commit_calls = 0

    def commit(self, *args, **kwargs):
        self.commit_calls += 1
        raise AssertionError("conditional plan scheduling must not mutate world")


class FakePlanScheduler:
    def __init__(self):
        self.calls = []
        self.by_key = {}

    def schedule(self, **kwargs):
        key = kwargs.get("idempotency_key")
        if key in self.by_key:
            return self.by_key[key]
        row = {"plan_id": f"plan_{len(self.by_key) + 1}", "proposal_id": kwargs.get("proposal_id"), "status": "planned"}
        self.by_key[key] = row
        self.calls.append(kwargs)
        return row


class SustainedConditionalPlanTest(unittest.TestCase):
    def test_sustained_presence_creates_one_plan_after_required_ticks(self):
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
            row = scheduler.register(
                condition={
                    "kind": "entity_in_region",
                    "entity_id": "nov",
                    "region_id": "village",
                    "sustain_ticks": 3,
                },
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                principal=PRINCIPAL,
                one_shot=True,
            )
            guarded.engine.cold_store.entities["nov"]["region_id"] = "village"
            self.assertEqual(scheduler.evaluate_tick(1)[0]["fire_count"], 0)
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 0)
            fired = scheduler.evaluate_tick(3)[0]
            self.assertEqual(fired["fire_count"], 1)
            self.assertEqual(fired["status"], "completed")
            self.assertEqual(fired["last_plan_id"], "plan_1")
            self.assertIsNotNone(fired["last_proposal_id"])
            proposal = proposals.get(fired["last_proposal_id"])
            self.assertEqual(proposal["status"], "approved")
            self.assertEqual(proposal["origin"], "conditional_event")
            self.assertEqual(len(plans.calls), 1)
            self.assertEqual(guarded.commit_calls, 0)
            self.assertEqual(scheduler.evaluate_tick(4), [])

    def test_broken_presence_resets_sustain_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposals = ProposalLedger(Path(tmp) / "proposals.jsonl")
            plans = FakePlanScheduler()
            dispatcher = ConditionalPlanDispatcher(proposals, plans)
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded, plan_dispatcher=dispatcher)
            scheduler.register(
                condition={"kind": "entity_in_region", "entity_id": "nov", "region_id": "village", "sustain_ticks": 3},
                intent={"intent": "move_to_entity", "actor_entity_id": "npc_01", "target_entity_id": "nov"},
                principal=PRINCIPAL,
                one_shot=True,
            )
            guarded.engine.cold_store.entities["nov"]["region_id"] = "village"
            scheduler.evaluate_tick(1)
            scheduler.evaluate_tick(2)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "forest"
            self.assertEqual(scheduler.evaluate_tick(3)[0]["fire_count"], 0)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "village"
            self.assertEqual(scheduler.evaluate_tick(4)[0]["fire_count"], 0)
            self.assertEqual(scheduler.evaluate_tick(5)[0]["fire_count"], 0)
            self.assertEqual(scheduler.evaluate_tick(6)[0]["fire_count"], 1)


if __name__ == "__main__":
    unittest.main()
