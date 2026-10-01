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

    def test_ephemeral_one_step_commits_world_without_plan_ledger_row(self) -> None:
        result = self.scheduler.execute_ephemeral_one_step(
            intent={
                "intent": "move_to_position",
                "actor_entity_id": "nov",
                "position": {"x": 25, "y": 10},
                "region_id": "r0",
                "idle_wander": True,
            },
            principal=self.principal,
            logical_tick=8,
            idempotency_key="idle:nov:2",
            priority=25,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.ledger.current(), [])
        self.assertEqual(
            self.store.get_entity("nov")["position"],
            {"x": 25.0, "y": 10.0},
        )
        self.assertTrue(result["world_event_id"])
        self.assertTrue(result["mutation_decision_id"])

    def test_ephemeral_multi_step_fails_closed_without_mutation(self) -> None:
        result = self.scheduler.execute_ephemeral_one_step(
            intent={
                "intent": "move_to_entity",
                "actor_entity_id": "nov",
                "target_entity_id": "bridge",
            },
            principal=self.principal,
            logical_tick=8,
            idempotency_key="idle:nov:cross",
            priority=25,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "requires_persistent")
        self.assertGreater(result["step_count"], 1)
        self.assertEqual(self.ledger.current(), [])
        self.assertEqual(self.store.get_entity("nov")["region_id"], "r0")

    def test_stage_observer_decomposes_schedule_and_tick(self) -> None:
        observed: list[tuple[str, int]] = []
        self.scheduler.stage_observer = lambda name, elapsed: observed.append(
            (name, elapsed)
        )
        plan = self.schedule_trip()
        result = self.scheduler.tick(plan["plan_id"])

        self.assertEqual(result["next_step_index"], 1)
        names = [name for name, _ in observed]
        self.assertIn("plan.schedule.plan", names)
        self.assertIn("plan.schedule.ledger_create", names)
        self.assertIn("plan.tick.lookup", names)
        self.assertIn("plan.tick.transition_running", names)
        self.assertIn("plan.tick.revalidate", names)
        self.assertIn("plan.tick.resolve", names)
        self.assertIn("plan.tick.narration", names)
        self.assertIn("plan.tick.guarded_commit", names)
        self.assertIn("plan.tick.mark_step_completed", names)
        self.assertTrue(all(elapsed >= 0 for _, elapsed in observed))

    def test_stage_observer_failure_never_controls_authoritative_execution(self) -> None:
        def broken_observer(name: str, elapsed: int) -> None:
            raise RuntimeError("observer unavailable")

        self.scheduler.stage_observer = broken_observer
        plan = self.schedule_trip()
        result = self.scheduler.tick(plan["plan_id"])

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["next_step_index"], 1)
        self.assertEqual(self.store.get_entity("nov")["region_id"], "r1")

    def test_tick_profiler_wires_same_observer_into_scheduler(self) -> None:
        source = (RUNTIME / "tick_driver_main.py").read_text(encoding="utf-8")
        self.assertIn(
            "scheduler.stage_observer = profiler.observe_stage",
            source,
        )

    def test_008h_rollout_is_observational_and_single_writer_only(self) -> None:
        script = (
            ROOT / "deploy" / "apply-plan-stage-profiling-008h.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("plan_scheduler.py", script)
        self.assertIn("tick_driver_main.py", script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("world-tick-profile.json", script)
        self.assertNotIn("hot_ledger_compactor", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)


if __name__ == "__main__":
    unittest.main()
