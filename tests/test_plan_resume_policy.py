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

PlanLedger = load("plan_ledger_resume_policy_test", RUNTIME / "plan_ledger.py").PlanLedger
PlanArbiter = load("plan_arbiter_resume_policy_test", RUNTIME / "plan_arbiter.py").PlanArbiter
PlanScheduler = load("plan_scheduler_resume_policy_test", RUNTIME / "plan_scheduler.py").PlanScheduler

from packages.spatial import DeterministicIntentPlanner, FileRegionColdStore, RegionCatalog


class DummyResolver:
    pass


class DummyGuarded:
    pass


def world_entities():
    return [
        {"id": "npc", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}},
        {"id": "nov", "type": "human", "region_id": "r1", "position": {"x": 100, "y": 0}},
    ]


def region_catalog():
    return RegionCatalog.from_world({
        "regions": [
            {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 60, "neighbors": ["r1"]},
            {"id": "r1", "center": {"x": 100, "y": 0}, "radius": 60, "neighbors": ["r0", "r2"]},
            {"id": "r2", "center": {"x": 200, "y": 0}, "radius": 60, "neighbors": ["r1"]},
        ]
    })


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc",
    "authority": "entity_agent",
    "subject_entity_id": "npc",
}


class PlanResumePolicyTest(unittest.TestCase):
    def make(self, tmp: Path):
        store = FileRegionColdStore(tmp / "cold")
        store.replace_all(world_entities())
        planner = DeterministicIntentPlanner(store, region_catalog())
        ledger = PlanLedger(tmp / "plans.jsonl")
        scheduler = PlanScheduler(ledger, planner, DummyResolver(), DummyGuarded())
        plan = scheduler.schedule(
            intent={"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "nov"},
            principal=PRINCIPAL,
            proposer_id="test",
            priority=10,
        )
        running = ledger.transition(plan["plan_id"], "running")
        waiting = ledger.transition(
            running["plan_id"],
            "waiting",
            waiting_reason="preempted",
            preempted_by_plan_id="urgent",
        )
        return store, scheduler, ledger, waiting

    def test_resume_when_goal_and_cursor_are_still_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store, scheduler, ledger, waiting = self.make(Path(tmpdir))
            decision = scheduler.assess_resume(waiting)
            self.assertEqual(decision["action"], "resume")
            arbiter = PlanArbiter(ledger, resume_evaluator=scheduler.assess_resume)
            result = arbiter.reconcile()
            self.assertEqual(result["resumptions"][0]["decision"], "resume")
            self.assertEqual(ledger.get(waiting["plan_id"])["status"], "running")

    def test_replan_when_target_moves_to_different_region(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store, scheduler, ledger, waiting = self.make(Path(tmpdir))
            target = store.get_entity("nov")
            assert target is not None
            target["region_id"] = "r2"
            target["position"] = {"x": 200, "y": 0}
            store.upsert(target)

            decision = scheduler.assess_resume(waiting)
            self.assertEqual(decision["action"], "replan")
            arbiter = PlanArbiter(ledger, resume_evaluator=scheduler.assess_resume)
            result = arbiter.reconcile()
            self.assertEqual(result["replans"][0]["decision"], "replan")
            current = ledger.get(waiting["plan_id"])
            self.assertEqual(current["status"], "replanning")
            self.assertEqual(current["next_step_index"], waiting["next_step_index"])

    def test_cancel_when_target_disappears(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store, scheduler, ledger, waiting = self.make(Path(tmpdir))
            store.remove("nov")

            decision = scheduler.assess_resume(waiting)
            self.assertEqual(decision["action"], "cancel")
            arbiter = PlanArbiter(ledger, resume_evaluator=scheduler.assess_resume)
            result = arbiter.reconcile()
            self.assertEqual(result["cancellations"][0]["decision"], "cancel")
            current = ledger.get(waiting["plan_id"])
            self.assertEqual(current["status"], "cancelled")
            self.assertEqual(current["next_step_index"], waiting["next_step_index"])


if __name__ == "__main__":
    unittest.main()
