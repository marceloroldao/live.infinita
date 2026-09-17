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

PlanLedger = load("plan_ledger_replanning_revision_test", RUNTIME / "plan_ledger.py").PlanLedger
PlanScheduler = load("plan_scheduler_replanning_revision_test", RUNTIME / "plan_scheduler.py").PlanScheduler

from packages.spatial import DeterministicIntentPlanner, FileRegionColdStore, Region, RegionCatalog


class DummyResolver:
    pass


class DummyGuarded:
    pass


PRINCIPAL = {
    "source": "world",
    "actor_id": "npc",
    "authority": "entity_agent",
    "subject_entity_id": "npc",
}


def catalog() -> RegionCatalog:
    return RegionCatalog([
        Region("r0", (0.0, 0.0), 60.0, neighbors=("r1",)),
        Region("r1", (100.0, 0.0), 60.0, neighbors=("r0", "r2")),
        Region("r2", (200.0, 0.0), 60.0, neighbors=("r1",)),
    ])


class PlanReplanningRevisionTest(unittest.TestCase):
    def make(self, tmp: Path):
        store = FileRegionColdStore(tmp / "cold")
        store.replace_all([
            {"id": "npc", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}},
            {"id": "nov", "type": "human", "region_id": "r1", "position": {"x": 100, "y": 0}},
        ])
        planner = DeterministicIntentPlanner(store, catalog())
        ledger = PlanLedger(tmp / "plans.jsonl")
        scheduler = PlanScheduler(ledger, planner, DummyResolver(), DummyGuarded())
        record = scheduler.schedule(
            intent={"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "nov"},
            principal=PRINCIPAL,
            proposer_id="test",
            priority=10,
        )
        record = ledger.transition(record["plan_id"], "running")
        record = ledger.transition(record["plan_id"], "replanning", last_error="target moved")
        return store, scheduler, ledger, record

    def test_replan_replaces_current_route_and_preserves_previous_revision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store, scheduler, ledger, record = self.make(Path(tmpdir))
            target = store.get_entity("nov")
            assert target is not None
            target["region_id"] = "r2"
            target["position"] = {"x": 200, "y": 0}
            store.upsert(target)

            updated = scheduler.replan(record["plan_id"])

            self.assertEqual(updated["status"], "running")
            self.assertEqual(updated["plan_revision"], 1)
            self.assertEqual(updated["next_step_index"], 0)
            self.assertEqual(updated["plan"]["goal_region_id"], "r2")
            self.assertEqual(updated["plan"]["region_path"], ["r0", "r1", "r2"])
            self.assertEqual(len(updated["plan_revision_history"]), 1)
            old = updated["plan_revision_history"][0]
            self.assertEqual(old["plan_revision"], 0)
            self.assertEqual(old["plan"]["goal_region_id"], "r1")
            self.assertEqual(old["reason"], "target moved")

    def test_completed_steps_survive_replan_and_new_steps_use_new_revision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store, scheduler, ledger, record = self.make(Path(tmpdir))
            # Simulate historical work already committed before the stale route.
            current = ledger.get(record["plan_id"])
            assert current is not None
            current = ledger.transition(
                current["plan_id"],
                "running",
                completed_steps=[{
                    "plan_revision": 0,
                    "step_index": 0,
                    "mutation_decision_id": "md_old",
                    "world_event_id": "evt_old",
                    "state_hash": "h_old",
                }],
                next_step_index=1,
            )
            current = ledger.transition(current["plan_id"], "replanning", last_error="route stale")

            target = store.get_entity("nov")
            assert target is not None
            target["region_id"] = "r2"
            target["position"] = {"x": 200, "y": 0}
            store.upsert(target)

            updated = scheduler.replan(current["plan_id"])
            self.assertEqual(updated["plan_revision"], 1)
            self.assertEqual(updated["next_step_index"], 0)
            self.assertEqual(len(updated["completed_steps"]), 1)
            self.assertEqual(updated["completed_steps"][0]["world_event_id"], "evt_old")

    def test_replan_cancels_when_semantic_goal_disappears(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store, scheduler, ledger, record = self.make(Path(tmpdir))
            store.remove("nov")

            updated = scheduler.replan(record["plan_id"])

            self.assertEqual(updated["status"], "cancelled")
            self.assertIn("replan failed", updated["last_error"])
            self.assertEqual(updated.get("plan_revision", 0), 0)
            self.assertEqual(updated.get("plan_revision_history", []), [])


if __name__ == "__main__":
    unittest.main()
