from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from plan_ledger import PlanLedger
from plan_scheduler import PlanScheduler
from packages.spatial import (
    AgentIntentResolver,
    DeterministicIntentPlanner,
    FileRegionColdStore,
    MutationPrincipal,
    Region,
    RegionCatalog,
)


class PlanSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        bootstrap = root / "bootstrap.json"
        bootstrap.write_text(json.dumps({
            "world_id": "scheduler-test",
            "version": 1,
            "sequence": 0,
            "regions": [
                {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 100, "neighbors": ["r1"]},
                {"id": "r1", "center": {"x": 200, "y": 0}, "radius": 100, "neighbors": ["r0", "r2"]},
                {"id": "r2", "center": {"x": 400, "y": 0}, "radius": 100, "neighbors": ["r1"]},
            ],
            "environment": {"period": "day", "biome": "forest"},
            "entities": [
                {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}, "properties": {}},
                {"id": "bridge", "type": "bridge", "region_id": "r2", "position": {"x": 440, "y": 10}, "properties": {}},
            ],
            "narration": {"text": ""},
        }), encoding="utf-8")
        self.store = FileRegionColdStore(root / "cold")
        self.engine = ColdAuthoritativeWorldEngine(bootstrap, root / "data", self.store)
        self.regions = RegionCatalog([
            Region("r0", (0, 0), 100, neighbors=("r1",)),
            Region("r1", (200, 0), 100, neighbors=("r0", "r2")),
            Region("r2", (400, 0), 100, neighbors=("r1",)),
        ])
        self.planner = DeterministicIntentPlanner(self.store, self.regions)
        self.resolver = AgentIntentResolver(self.store)
        self.guarded = GuardedMutationService(
            self.engine,
            decision_log_file=root / "data" / "mutation-decisions.jsonl",
        )
        self.ledger_path = root / "data" / "plan-ledger.jsonl"
        self.ledger = PlanLedger(self.ledger_path)
        self.scheduler = PlanScheduler(self.ledger, self.planner, self.resolver, self.guarded)
        self.principal = MutationPrincipal(
            source="agent",
            actor_id="nov-agent",
            authority="entity_agent",
            subject_entity_id="nov",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def schedule_trip(self) -> dict:
        return self.scheduler.schedule(
            intent={"intent": "move_to_entity", "actor_entity_id": "nov", "target_entity_id": "bridge"},
            principal=self.principal,
            proposer_id="nov-agent",
            idempotency_key="nov-to-bridge",
        )

    def test_one_tick_executes_only_one_step(self) -> None:
        plan = self.schedule_trip()
        result = self.scheduler.tick(plan["plan_id"])
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["next_step_index"], 1)
        self.assertEqual(len(result["completed_steps"]), 1)
        nov = self.store.get_entity("nov")
        self.assertEqual(nov["region_id"], "r1")
        self.assertEqual(self.engine.load_world()["sequence"], 1)

    def test_restart_resumes_from_next_uncommitted_step(self) -> None:
        plan = self.schedule_trip()
        first = self.scheduler.tick(plan["plan_id"])
        self.assertEqual(first["next_step_index"], 1)

        reopened_ledger = PlanLedger(self.ledger_path)
        restarted = PlanScheduler(reopened_ledger, self.planner, self.resolver, self.guarded)
        second = restarted.tick(plan["plan_id"])
        self.assertEqual(second["next_step_index"], 2)
        self.assertEqual(len(second["completed_steps"]), 2)
        self.assertEqual(self.engine.load_world()["sequence"], 2)
        self.assertEqual(self.store.get_entity("nov")["region_id"], "r2")

    def test_trip_completes_after_three_ticks(self) -> None:
        plan = self.schedule_trip()
        self.scheduler.tick(plan["plan_id"])
        self.scheduler.tick(plan["plan_id"])
        final = self.scheduler.tick(plan["plan_id"])
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["next_step_index"], 3)
        self.assertEqual(len(final["completed_steps"]), 3)
        nov = self.store.get_entity("nov")
        self.assertEqual(nov["position"], {"x": 440.0, "y": 10.0})
        self.assertTrue(self.engine.verify_replay()["ok"])

    def test_external_divergence_moves_plan_to_replanning(self) -> None:
        plan = self.schedule_trip()
        self.scheduler.tick(plan["plan_id"])
        self.engine.commit_operations([
            {"op": "move", "entity_id": "nov", "position": {"x": 0, "y": 0}, "region_id": "r0"}
        ], source="system", context={"test": "external divergence"})
        stale = self.scheduler.tick(plan["plan_id"])
        self.assertEqual(stale["status"], "replanning")
        self.assertEqual(stale["next_step_index"], 1)
        self.assertIn("plan stale", stale["last_error"])

    def test_idempotent_schedule_does_not_duplicate_plan(self) -> None:
        a = self.schedule_trip()
        b = self.schedule_trip()
        self.assertEqual(a["plan_id"], b["plan_id"])
        self.assertEqual(len(self.ledger.current()), 1)


if __name__ == "__main__":
    unittest.main()
