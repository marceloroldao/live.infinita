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

NpcNeedScheduler = load("npc_need_scheduler_test", RUNTIME / "npc_need_scheduler.py").NpcNeedScheduler
NpcCompositeStrategy = load("npc_composite_strategy_test_sched", RUNTIME / "npc_composite_strategy.py").NpcCompositeStrategy
NpcStrategyCompiler = load("npc_strategy_compiler_test_sched", RUNTIME / "npc_strategy_compiler.py").NpcStrategyCompiler


class FakeStore:
    def __init__(self, entities):
        self.entities = {row["id"]: row for row in entities}

    def get_entity(self, entity_id):
        row = self.entities.get(entity_id)
        return dict(row) if row is not None else None


class FakePlanner:
    def __init__(self, store):
        self.store = store
        self.regions = None


class FakeProposalLedger:
    def __init__(self):
        self.rows = {}
        self.calls = []

    def propose(self, **kwargs):
        key = kwargs.get("idempotency_key")
        for row in self.rows.values():
            if row.get("idempotency_key") == key:
                return dict(row)
        proposal_id = f"proposal_{len(self.rows)+1}"
        row = {"proposal_id": proposal_id, "status": "proposed", **kwargs}
        self.rows[proposal_id] = row
        self.calls.append(("propose", kwargs))
        return dict(row)

    def approve(self, proposal_id, **kwargs):
        row = dict(self.rows[proposal_id])
        row["status"] = "approved"
        self.rows[proposal_id] = row
        self.calls.append(("approve", {"proposal_id": proposal_id, **kwargs}))
        return dict(row)


class FakePlanScheduler:
    def __init__(self, store):
        self.planner = FakePlanner(store)
        self.calls = []

    def schedule(self, **kwargs):
        self.calls.append(kwargs)
        return {"plan_id": f"plan_{len(self.calls)}", "status": "planned", "priority": kwargs.get("priority", 0)}


class FakeCompositeProvider:
    def candidates(self, **kwargs):
        return [{
            "strategy_id": "wait_then_direct",
            "phases": [
                {"kind": "wait_ticks", "ticks": 2},
                {"kind": "move_to_entity", "target_entity_id": kwargs["target_entity_id"]},
            ],
            "predicted_satisfaction": kwargs["predicted_satisfaction"],
            "estimated_hops": 0,
            "estimated_risk": 0.0,
            "wait_ticks": 2,
        }]

    def choose(self, candidates):
        return dict(candidates[0]), [dict(candidates[0])]


class FakeStrategyExecutor:
    def __init__(self):
        self.calls = []

    def start(self, strategy_plan, **kwargs):
        self.calls.append({"strategy_plan": strategy_plan, **kwargs})
        return {"strategy_execution_id": f"exec_{len(self.calls)}", "status": "running"}


class NpcNeedSchedulerTest(unittest.TestCase):
    def make(self, tmp: Path, needs: dict[str, float], **targets):
        npc = {
            "id": "npc",
            "type": "human",
            "region_id": "r0",
            "position": {"x": 0, "y": 0},
            "properties": {"needs": needs, **targets},
        }
        target_ids = {value for key, value in targets.items() if key.endswith("_target_entity_id")}
        entities = [npc] + [
            {"id": target_id, "type": "place", "region_id": "r0", "position": {"x": 10, "y": 0}, "properties": {}}
            for target_id in sorted(target_ids)
        ]
        store = FakeStore(entities)
        proposals = FakeProposalLedger()
        plans = FakePlanScheduler(store)
        scheduler = NpcNeedScheduler(
            tmp / "needs.jsonl",
            proposals,
            plans,
            npc_ids=["npc"],
            threshold=0.70,
            cooldown_ticks=10,
        )
        return scheduler, proposals, plans

    def test_constructor_repairs_one_legacy_middle_jsonl_fragment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "needs.jsonl"
            original = (
                '{"npc_id":"npc","need":"energy","status":"scheduled","tick":1}\n'
                '{"npc_id":\n'
                '{"npc_id":"npc","need":"energy","status":"scheduled","tick":2}\n'
            )
            path.write_text(original, encoding="utf-8")
            store = FakeStore([{
                "id": "npc", "type": "human", "region_id": "r0",
                "position": {"x": 0, "y": 0}, "properties": {"needs": {}},
            }])
            scheduler = NpcNeedScheduler(
                path, FakeProposalLedger(), FakePlanScheduler(store), npc_ids=["npc"]
            )
            self.assertEqual([row["tick"] for row in scheduler.history()], [1, 2])
            self.assertEqual(
                path.with_suffix(".jsonl.legacy-repair-v1.bak").read_text(encoding="utf-8"),
                original,
            )
            self.assertEqual(
                path.with_suffix(".jsonl.legacy-repair-v1.corrupt").read_text(encoding="utf-8"),
                '{"npc_id":\n',
            )

    def test_safety_utility_beats_higher_curiosity_severity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans = self.make(
                Path(tmpdir),
                {"safety": 0.80, "energy": 0.0, "social": 0.0, "curiosity": 1.0},
                safety_target_entity_id="safe_place",
                curiosity_target_entity_id="interesting_place",
            )
            result = scheduler.evaluate_tick(1)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["need"], "safety")
            self.assertEqual(result[0]["priority"], 1000)
            self.assertAlmostEqual(result[0]["utility"], 800.0)
            self.assertEqual(plans.calls[0]["intent"]["target_entity_id"], "safe_place")
            self.assertEqual(plans.calls[0]["priority"], 1000)
            self.assertEqual(len(proposals.calls), 2)

    def test_below_threshold_emits_no_proposal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans = self.make(
                Path(tmpdir),
                {"safety": 0.20, "energy": 0.30, "social": 0.60, "curiosity": 0.69},
            )
            self.assertEqual(scheduler.evaluate_tick(1), [])
            self.assertEqual(plans.calls, [])
            self.assertEqual(proposals.calls, [])

    def test_cooldown_prevents_repeated_plan_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans = self.make(
                Path(tmpdir),
                {"energy": 0.90},
                rest_target_entity_id="bed",
            )
            first = scheduler.evaluate_tick(5)
            second = scheduler.evaluate_tick(8)
            self.assertEqual(first[0]["status"], "scheduled")
            self.assertEqual(second[0]["status"], "cooldown")
            self.assertEqual(len(plans.calls), 1)
            third = scheduler.evaluate_tick(15)
            self.assertEqual(third[0]["status"], "scheduled")
            self.assertEqual(len(plans.calls), 2)

    def test_missing_target_is_audited_without_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans = self.make(
                Path(tmpdir),
                {"social": 0.95},
            )
            row = scheduler.evaluate_tick(1)[0]
            self.assertEqual(row["status"], "no_target")
            self.assertIsNone(row["proposal_id"])
            self.assertEqual(plans.calls, [])
            self.assertEqual(proposals.calls, [])
            self.assertEqual(len(scheduler.history()), 1)

    def test_composite_stack_starts_strategy_instead_of_direct_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans = self.make(
                Path(tmpdir),
                {"energy": 0.90},
                rest_target_entity_id="bed",
            )
            executor = FakeStrategyExecutor()
            scheduler.composite_strategy_provider = FakeCompositeProvider()
            scheduler.strategy_compiler = NpcStrategyCompiler()
            scheduler.strategy_executor = executor

            row = scheduler.evaluate_tick(1)[0]
            self.assertEqual(row["status"], "scheduled")
            self.assertEqual(row["strategy_id"], "wait_then_direct")
            self.assertEqual(row["strategy_execution_id"], "exec_1")
            self.assertIsNone(row["plan_id"])
            self.assertEqual(plans.calls, [])
            self.assertEqual(executor.calls[0]["proposal_id"], row["proposal_id"])
            phases = executor.calls[0]["strategy_plan"]["phases"]
            self.assertFalse(phases[0]["intent"]["need_outcome_eligible"])
            self.assertTrue(phases[1]["intent"]["need_outcome_eligible"])


if __name__ == "__main__":
    unittest.main()
