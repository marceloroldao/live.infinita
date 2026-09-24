from __future__ import annotations

import importlib.util
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
from intent_plan_executor import DeterministicIntentPlanExecutor
from mutation_gate_service import GuardedMutationService
from packages.spatial import (
    AgentIntentResolver,
    DeterministicIntentPlanner,
    FileRegionColdStore,
    MutationPrincipal,
    Region,
    RegionCatalog,
)


class IntentPlanExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bootstrap = root / "bootstrap.json"
        self.data_dir = root / "data"
        self.store = FileRegionColdStore(root / "cold")
        self.bootstrap.write_text(json.dumps({
            "world_id": "plan-test",
            "version": 1,
            "sequence": 0,
            "regions": [
                {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 200, "neighbors": ["r1"]},
                {"id": "r1", "center": {"x": 500, "y": 0}, "radius": 200, "neighbors": ["r0", "r2"]},
                {"id": "r2", "center": {"x": 1000, "y": 0}, "radius": 200, "neighbors": ["r1"]},
            ],
            "environment": {"period": "day", "biome": "forest"},
            "entities": [
                {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}, "properties": {}},
                {"id": "bridge", "type": "bridge", "region_id": "r2", "position": {"x": 1000, "y": 25}, "properties": {}},
            ],
            "narration": {"text": ""},
        }), encoding="utf-8")
        self.engine = ColdAuthoritativeWorldEngine(self.bootstrap, self.data_dir, self.store)
        self.regions = RegionCatalog([
            Region("r0", (0.0, 0.0), 200.0, neighbors=("r1",)),
            Region("r1", (500.0, 0.0), 200.0, neighbors=("r0", "r2")),
            Region("r2", (1000.0, 0.0), 200.0, neighbors=("r1",)),
        ])
        self.planner = DeterministicIntentPlanner(self.store, self.regions)
        self.resolver = AgentIntentResolver(self.store)
        self.guarded = GuardedMutationService(
            self.engine,
            decision_log_file=self.data_dir / "mutation-decisions.jsonl",
        )
        self.executor = DeterministicIntentPlanExecutor(self.planner, self.resolver, self.guarded)
        self.principal = MutationPrincipal(
            source="agent",
            actor_id="nov-agent",
            authority="entity_agent",
            subject_entity_id="nov",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_nov_crosses_regions_and_arrives_at_bridge(self) -> None:
        plan = self.planner.plan({
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
        })
        result = self.executor.execute(plan, principal=self.principal)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.completed_steps, 3)
        self.assertEqual(len(result.world_event_ids), 3)
        self.assertEqual(len(result.mutation_decision_ids), 3)
        nov = self.store.get_entity("nov")
        assert nov is not None
        self.assertEqual(nov["region_id"], "r2")
        self.assertEqual(nov["position"], {"x": 1000.0, "y": 25.0})
        self.assertTrue(self.engine.verify_replay()["ok"])

    def test_policy_rejection_stops_before_mutation(self) -> None:
        plan = self.planner.plan({
            "intent": "move_to_position",
            "actor_entity_id": "nov",
            "position": {"x": 100, "y": 0},
            "region_id": "r0",
        })
        observer = MutationPrincipal(source="agent", actor_id="viewer", authority="observer")
        before = self.engine.load_world()["state_hash"]
        result = self.executor.execute(plan, principal=observer)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.completed_steps, 0)
        self.assertEqual(self.engine.load_world()["state_hash"], before)
        self.assertEqual(self.store.get_entity("nov")["position"], {"x": 0, "y": 0})

    def test_stale_plan_stops_when_actor_region_changes_before_execution(self) -> None:
        plan = self.planner.plan({
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
        })
        nov = self.store.get_entity("nov")
        assert nov is not None
        nov["region_id"] = "r2"
        nov["position"] = {"x": 900, "y": 0}
        self.store.upsert(nov)
        before = self.engine.load_world()["state_hash"]
        result = self.executor.execute(plan, principal=self.principal)
        self.assertEqual(result.status, "stale")
        self.assertEqual(result.completed_steps, 0)
        self.assertEqual(self.engine.load_world()["state_hash"], before)


if __name__ == "__main__":
    unittest.main()
