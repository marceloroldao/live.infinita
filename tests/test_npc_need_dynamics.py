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


NpcNeedDynamics = load("npc_need_dynamics_test", RUNTIME / "npc_need_dynamics.py").NpcNeedDynamics
NpcNeedScheduler = load("npc_need_scheduler_provider_test", RUNTIME / "npc_need_scheduler.py").NpcNeedScheduler


class FakeStore:
    def __init__(self, entities):
        self.entities = {row["id"]: row for row in entities}

    def get_entity(self, entity_id):
        row = self.entities.get(entity_id)
        if row is None:
            return None
        import copy
        return copy.deepcopy(row)


class FakePlanner:
    def __init__(self, store):
        self.store = store


class FakePlanScheduler:
    def __init__(self, store):
        self.planner = FakePlanner(store)
        self.calls = []

    def schedule(self, **kwargs):
        self.calls.append(kwargs)
        return {"plan_id": f"plan_{len(self.calls)}", "status": "planned"}


class FakeProposals:
    def __init__(self):
        self.rows = {}

    def propose(self, **kwargs):
        proposal_id = f"proposal_{len(self.rows)+1}"
        row = {"proposal_id": proposal_id, "status": "proposed", **kwargs}
        self.rows[proposal_id] = row
        return dict(row)

    def approve(self, proposal_id, **kwargs):
        row = dict(self.rows[proposal_id])
        row["status"] = "approved"
        self.rows[proposal_id] = row
        return dict(row)


def entities(*, region="r0", danger=0.0):
    return [
        {
            "id": "npc",
            "type": "human",
            "region_id": region,
            "position": {"x": 0, "y": 0},
            "properties": {
                "needs": {"safety": 0.2, "energy": 0.5, "social": 0.5, "curiosity": 0.5},
                "danger_level": danger,
                "rest_target_entity_id": "bed",
                "social_target_entity_id": "friend",
                "curiosity_target_entity_id": "landmark",
                "safety_target_entity_id": "shelter",
            },
        },
        {"id": "bed", "type": "place", "region_id": "r0", "position": {"x": 1, "y": 0}},
        {"id": "friend", "type": "human", "region_id": "r0", "position": {"x": 2, "y": 0}},
        {"id": "landmark", "type": "place", "region_id": "r0", "position": {"x": 3, "y": 0}},
        {"id": "shelter", "type": "place", "region_id": "r0", "position": {"x": 4, "y": 0}},
    ]


class NpcNeedDynamicsTest(unittest.TestCase):
    def test_same_tick_is_idempotent_and_restart_does_not_catch_up(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "need-state.json"
            store = FakeStore(entities(region="r1"))
            dynamics = NpcNeedDynamics(path, store, npc_ids=["npc"])
            first = dynamics.advance_tick(1)[0]["after"]
            self.assertEqual(dynamics.advance_tick(1), [])

            restarted = NpcNeedDynamics(path, store, npc_ids=["npc"])
            later = restarted.advance_tick(100)[0]["after"]
            self.assertAlmostEqual(later["energy"] - first["energy"], 0.002, places=6)
            self.assertEqual(restarted.snapshot()["last_tick"], 100)

    def test_context_relief_reduces_energy_social_and_curiosity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FakeStore(entities(region="r0"))
            dynamics = NpcNeedDynamics(Path(tmpdir) / "need-state.json", store, npc_ids=["npc"])
            after = dynamics.advance_tick(1)[0]["after"]
            self.assertAlmostEqual(after["energy"], 0.48, places=6)
            self.assertAlmostEqual(after["social"], 0.485, places=6)
            self.assertAlmostEqual(after["curiosity"], 0.48, places=6)
            self.assertLess(after["safety"], 0.2)

    def test_danger_increases_safety_need(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FakeStore(entities(region="r1", danger=1.0))
            dynamics = NpcNeedDynamics(Path(tmpdir) / "need-state.json", store, npc_ids=["npc"])
            after = dynamics.advance_tick(1)[0]["after"]
            self.assertAlmostEqual(after["safety"], 0.217, places=6)

    def test_scheduler_reads_compact_dynamic_state_provider(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            store = FakeStore(entities(region="r1"))
            dynamics = NpcNeedDynamics(
                tmp / "need-state.json",
                store,
                npc_ids=["npc"],
                rates={"energy": 0.50, "social": 0.0, "curiosity": 0.0, "safety": 0.0},
            )
            dynamics.advance_tick(1)
            plans = FakePlanScheduler(store)
            proposals = FakeProposals()
            scheduler = NpcNeedScheduler(
                tmp / "need-decisions.jsonl",
                proposals,
                plans,
                npc_ids=["npc"],
                threshold=0.70,
                need_state_provider=dynamics,
            )
            rows = scheduler.evaluate_tick(1)
            self.assertEqual(rows[0]["need"], "energy")
            self.assertEqual(rows[0]["status"], "scheduled")
            self.assertEqual(plans.calls[0]["intent"]["target_entity_id"], "bed")


if __name__ == "__main__":
    unittest.main()
