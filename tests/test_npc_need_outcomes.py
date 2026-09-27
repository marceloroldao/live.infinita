from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
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

NpcNeedDynamics = load("npc_need_dynamics_outcomes_test", RUNTIME / "npc_need_dynamics.py").NpcNeedDynamics
NpcNeedOutcomeProcessor = load("npc_need_outcomes_test", RUNTIME / "npc_need_outcomes.py").NpcNeedOutcomeProcessor
PlanLedger = load("plan_ledger_need_outcomes_test", RUNTIME / "plan_ledger.py").PlanLedger


class FakeStore:
    def __init__(self):
        self.entities = {
            "npc": {
                "id": "npc",
                "type": "human",
                "region_id": "r0",
                "position": {"x": 0, "y": 0},
                "properties": {"needs": {"energy": 0.90, "social": 0.80}},
            }
        }

    def get_entity(self, entity_id):
        row = self.entities.get(entity_id)
        return dict(row) if row is not None else None


class NpcNeedOutcomeTest(unittest.TestCase):
    def make(self, tmp: Path):
        store = FakeStore()
        dynamics = NpcNeedDynamics(tmp / "need-state.json", store, npc_ids=["npc"])
        dynamics.advance_tick(1)
        ledger = PlanLedger(tmp / "plans.jsonl")
        processor = NpcNeedOutcomeProcessor(tmp / "outcomes.jsonl", ledger, dynamics)
        return dynamics, ledger, processor

    @staticmethod
    def complete_plan(ledger: PlanLedger, *, need: str | None, status: str = "completed"):
        intent = {"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "target"}
        if need is not None:
            intent["need"] = need
        plan = ledger.create(
            proposal_id="proposal_1",
            proposer_id="npc:npc",
            principal={"source": "npc_need", "actor_id": "npc", "authority": "entity_agent", "subject_entity_id": "npc"},
            intent=intent,
            plan={
                "intent_type": "move_to_entity",
                "actor_entity_id": "npc",
                "source_region_id": "r0",
                "goal_region_id": "r0",
                "region_path": ["r0"],
                "steps": [{"step_index": 0, "kind": "goal", "intent": intent, "expected_region_id": "r0", "goal_region_id": "r0"}],
            },
        )
        running = ledger.transition(plan["plan_id"], "running")
        if status == "completed":
            return ledger.mark_step_completed(
                running["plan_id"],
                step_index=0,
                mutation_decision_id="decision_1",
                world_event_id="event_1",
                state_hash="hash_1",
            )
        return ledger.transition(running["plan_id"], status, last_error="test")

    def test_completed_energy_plan_reduces_need_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, ledger, processor = self.make(Path(tmpdir))
            before = dynamics.get_needs("npc")["energy"]
            plan = self.complete_plan(ledger, need="energy")
            first = processor.process_completed()
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["plan_id"], plan["plan_id"])
            after = dynamics.get_needs("npc")["energy"]
            self.assertAlmostEqual(after, max(0.0, before - 0.40))
            self.assertEqual(processor.process_completed(), [])
            self.assertAlmostEqual(dynamics.get_needs("npc")["energy"], after)

    def test_non_need_plan_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, ledger, processor = self.make(Path(tmpdir))
            before = dynamics.get_needs("npc")
            self.complete_plan(ledger, need=None)
            self.assertEqual(processor.process_completed(), [])
            self.assertEqual(dynamics.get_needs("npc"), before)

    def test_failed_or_cancelled_plan_does_not_satisfy(self):
        for terminal in ("failed", "cancelled"):
            with self.subTest(terminal=terminal), tempfile.TemporaryDirectory() as tmpdir:
                dynamics, ledger, processor = self.make(Path(tmpdir))
                before = dynamics.get_needs("npc")["social"]
                self.complete_plan(ledger, need="social", status=terminal)
                self.assertEqual(processor.process_completed(), [])
                self.assertAlmostEqual(dynamics.get_needs("npc")["social"], before)

    def test_dynamics_satisfy_is_idempotent_by_outcome_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, _, _ = self.make(Path(tmpdir))
            before = dynamics.get_needs("npc")["social"]
            first = dynamics.satisfy("npc", "social", 0.20, outcome_id="same")
            second = dynamics.satisfy("npc", "social", 0.20, outcome_id="same")
            self.assertEqual(first, second)
            self.assertAlmostEqual(dynamics.get_needs("npc")["social"], max(0.0, before - 0.20))


    def test_second_pass_uses_candidate_and_processed_indexes_without_replaying(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, ledger, processor = self.make(Path(tmpdir))
            self.complete_plan(ledger, need="energy")
            self.assertEqual(len(processor.process_completed()), 1)
            with patch.object(ledger, "current", side_effect=AssertionError("full plan copy")), \
                 patch.object(processor, "history", side_effect=AssertionError("full outcome replay")):
                self.assertEqual(processor.process_completed(), [])
            self.assertEqual(len(processor.history()), 1)

    def test_external_outcome_append_invalidates_index_and_avoids_reapplying(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, ledger, processor = self.make(Path(tmpdir))
            completed = self.complete_plan(ledger, need="social")
            before = dynamics.get_needs("npc")["social"]
            self.assertEqual(processor._processed_ids(), set())
            with processor.path.open("ab") as fh:
                fh.write((json.dumps({"plan_id": completed["plan_id"], "status": "applied"}) + "\n").encode("utf-8"))
            self.assertEqual(processor.process_completed(), [])
            self.assertAlmostEqual(dynamics.get_needs("npc")["social"], before)
            self.assertEqual(processor._processed_ids(), {completed["plan_id"]})
            replacement = Path(tmpdir) / "other-outcomes.jsonl"
            replacement.write_text("", encoding="utf-8")
            os.replace(replacement, processor.path)
            self.assertEqual(processor._processed_ids(), set())
            self.assertEqual(len(processor.process_completed()), 1)

    def test_restart_recovers_processed_ids_from_durable_outcomes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, ledger, processor = self.make(Path(tmpdir))
            self.complete_plan(ledger, need="energy")
            self.assertEqual(len(processor.process_completed()), 1)
            rebooted = NpcNeedOutcomeProcessor(processor.path, ledger, dynamics)
            with patch.object(ledger, "current", side_effect=AssertionError("full plan copy")):
                self.assertEqual(rebooted.process_completed(), [])
            self.assertEqual(len(rebooted.history()), 1)

    def test_applied_lookup_is_detached_and_tracks_external_ledger_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dynamics, ledger, processor = self.make(Path(tmpdir))
            plan = self.complete_plan(ledger, need="energy")
            applied = processor.process_completed()[0]
            self.assertEqual(processor.get_applied(plan["plan_id"]), applied)
            with patch.object(processor, "history", side_effect=AssertionError("unexpected replay")):
                cached = processor.get_applied(plan["plan_id"])
                cached["outcome"]["before"] = 999
                self.assertEqual(processor.get_applied(plan["plan_id"]), applied)
            new_id = "external-plan"
            with processor.path.open("ab") as fh:
                fh.write((json.dumps({"plan_id": new_id, "status": "applied", "outcome": {"before": 0.8}}) + "\n").encode("utf-8"))
            self.assertEqual(processor.get_applied(new_id)["outcome"]["before"], 0.8)
            replacement = Path(tmpdir) / "replacement-audit.jsonl"
            replacement.write_text(json.dumps({"plan_id": "replacement", "status": "applied"}) + "\n", encoding="utf-8")
            os.replace(replacement, processor.path)
            self.assertIsNone(processor.get_applied(new_id))
            self.assertEqual(processor.get_applied("replacement")["status"], "applied")



if __name__ == "__main__":
    unittest.main()
