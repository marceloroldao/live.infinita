from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_need_dynamics import NpcNeedDynamics
from conditional_event_scheduler import ConditionalEventScheduler

from tests.test_npc_need_dynamics import FakeStore, entities
from tests.test_conditional_event_scheduler import FakeGuarded, PRINCIPAL


class StorageTailStageProfiling008MTests(unittest.TestCase):
    def test_need_dynamics_profiles_hot_checkpoint_write_and_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observed: list[tuple[str, int]] = []
            state = Path(tmpdir) / "need-state.json"
            dynamics = NpcNeedDynamics(
                state,
                FakeStore(entities(region="r1")),
                npc_ids=["npc"],
                stage_observer=lambda name, elapsed: observed.append(
                    (name, elapsed)
                ),
            )
            result = dynamics.advance_tick(1)
            self.assertEqual(len(result), 1)
            names = [name for name, _ in observed]
            self.assertIn("need.dynamics.advance.save", names)
            self.assertIn("need.dynamics.save.write_tmp", names)
            self.assertIn("need.dynamics.save.replace", names)
            self.assertTrue(all(elapsed >= 0 for _, elapsed in observed))
            persisted = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(persisted["schema"], "npc_need_state_v2")
            self.assertEqual(persisted["last_tick"], 1)

    def test_need_dynamics_observer_failure_is_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir) / "need-state.json"
            dynamics = NpcNeedDynamics(
                state,
                FakeStore(entities(region="r1")),
                npc_ids=["npc"],
                stage_observer=lambda *_: (_ for _ in ()).throw(
                    RuntimeError("observer unavailable")
                ),
            )
            result = dynamics.advance_tick(1)
            self.assertEqual(len(result), 1)
            self.assertEqual(
                json.loads(state.read_text(encoding="utf-8"))["last_tick"],
                1,
            )

    def test_conditional_profiles_current_condition_commit_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observed: list[tuple[str, int]] = []
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(
                Path(tmpdir) / "conditional.jsonl",
                guarded,
                stage_observer=lambda name, elapsed: observed.append(
                    (name, elapsed)
                ),
            )
            scheduler.register(
                condition={
                    "kind": "world_equals",
                    "path": ["environment", "period"],
                    "value": "day",
                },
                operations=[
                    {
                        "op": "set",
                        "entity_id": "lamp",
                        "path": ["properties", "lit"],
                        "value": True,
                    }
                ],
                principal=PRINCIPAL,
                one_shot=True,
            )
            result = scheduler.evaluate_tick(1)
            self.assertEqual(result[0]["status"], "completed")
            names = [name for name, _ in observed]
            self.assertIn("conditional.evaluate.current", names)
            self.assertIn("conditional.evaluate.condition", names)
            self.assertIn("conditional.condition.load_world", names)
            self.assertIn("conditional.evaluate.guarded_commit", names)
            self.assertIn("conditional.evaluate.append", names)
            self.assertTrue(all(elapsed >= 0 for _, elapsed in observed))

    def test_conditional_profiles_cache_only_for_stable_false_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observed: list[tuple[str, int]] = []
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(
                Path(tmpdir) / "conditional.jsonl",
                guarded,
                stage_observer=lambda name, elapsed: observed.append(
                    (name, elapsed)
                ),
            )
            scheduler.register(
                condition={
                    "kind": "world_equals",
                    "path": ["environment", "period"],
                    "value": "night",
                },
                operations=[
                    {
                        "op": "set",
                        "entity_id": "lamp",
                        "path": ["properties", "lit"],
                        "value": True,
                    }
                ],
                principal=PRINCIPAL,
            )
            result = scheduler.evaluate_tick(1)
            self.assertEqual(result[0]["fire_count"], 0)
            names = [name for name, _ in observed]
            self.assertIn("conditional.evaluate.current", names)
            self.assertIn("conditional.evaluate.condition", names)
            self.assertIn("conditional.evaluate.cache_only", names)

    def test_conditional_observer_failure_is_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(
                Path(tmpdir) / "conditional.jsonl",
                guarded,
                stage_observer=lambda *_: (_ for _ in ()).throw(
                    RuntimeError("observer unavailable")
                ),
            )
            scheduler.register(
                condition={
                    "kind": "world_equals",
                    "path": ["environment", "period"],
                    "value": "day",
                },
                operations=[
                    {
                        "op": "set",
                        "entity_id": "lamp",
                        "path": ["properties", "lit"],
                        "value": True,
                    }
                ],
                principal=PRINCIPAL,
                one_shot=True,
            )
            result = scheduler.evaluate_tick(1)
            self.assertEqual(result[0]["status"], "completed")
            self.assertTrue(
                guarded.engine.cold_store.entities["lamp"]["properties"]["lit"]
            )

    def test_tick_profiler_wires_both_components(self) -> None:
        source = (RUNTIME / "tick_driver_main.py").read_text(encoding="utf-8")
        self.assertIn('"npc_need_dynamics"', source)
        self.assertIn('"conditional_event_scheduler"', source)
        self.assertIn(
            "component.stage_observer = profiler.observe_stage",
            source,
        )

    def test_source_contract_preserves_storage_semantics(self) -> None:
        need = (RUNTIME / "npc_need_dynamics.py").read_text(encoding="utf-8")
        conditional = (
            RUNTIME / "conditional_event_scheduler.py"
        ).read_text(encoding="utf-8")
        self.assertIn("tmp.replace(self.path)", need)
        self.assertIn("os.fsync(fd)", need)
        self.assertIn("need.dynamics.save.write_tmp", need)
        self.assertIn("need.dynamics.save.replace", need)
        self.assertIn("need.dynamics.outcome.write", need)
        self.assertIn("need.dynamics.outcome.fsync", need)
        self.assertIn("conditional.condition.load_world", conditional)
        self.assertIn("conditional.evaluate.current", conditional)
        self.assertIn("conditional.evaluate.condition", conditional)
        self.assertIn("conditional.evaluate.append", conditional)
        self.assertIn("conditional.evaluate.cache_only", conditional)

    def test_rollout_only_restarts_single_writer(self) -> None:
        script = (
            ROOT / "deploy" / "apply-storage-tail-profiling-008m.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("npc_need_dynamics.py", script)
        self.assertIn("conditional_event_scheduler.py", script)
        self.assertIn("tick_driver_main.py", script)
        self.assertIn("npc-need-state.outcomes.jsonl", script)
        self.assertIn("plans.jsonl.index.sqlite3", script)
        self.assertIn("proposals.jsonl.index.sqlite3", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)


if __name__ == "__main__":
    unittest.main()
