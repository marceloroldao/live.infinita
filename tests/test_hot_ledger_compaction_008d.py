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

from conditional_event_scheduler import ConditionalEventScheduler
from hot_ledger_compactor import compact_conditional, compact_plans, compact_proposals
from plan_ledger import PlanLedger
from proposal_ledger import ProposalLedger


class FakeStore:
    def __init__(self) -> None:
        self.entities = {
            "nov": {
                "id": "nov",
                "region_id": "clearing",
                "properties": {},
            }
        }

    def get_entity(self, entity_id: str):
        value = self.entities.get(entity_id)
        return dict(value) if value else None


class FakeEngine:
    def __init__(self) -> None:
        self.cold_store = FakeStore()
        self.world = {
            "environment": {"period": "day"},
            "state_hash": "h0",
        }
        self.sequence = 0

    def load_world(self):
        return dict(self.world)

    def commit_operations(self, operations, *, source, context, narration):
        self.sequence += 1
        self.world["state_hash"] = f"h{self.sequence}"
        return (
            {"event_id": f"evt_{self.sequence}"},
            {"operations": operations},
            dict(self.world),
        )


class AcceptGate:
    def decide(self, operations, principal):
        from packages.spatial import MutationDecision, MutationPrincipal
        if isinstance(principal, dict):
            principal = MutationPrincipal.from_dict(principal)
        return MutationDecision(True, "accepted", principal, tuple(operations))


def guarded():
    from mutation_gate_service import GuardedMutationService
    return GuardedMutationService(FakeEngine(), gate=AcceptGate())


PRINCIPAL = {"source": "system", "actor_id": "world", "authority": "system"}


class HotLedgerCompaction008DTests(unittest.TestCase):
    def test_stable_condition_ticks_do_not_grow_durable_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conditional.jsonl"
            service = guarded()
            scheduler = ConditionalEventScheduler(path, service)
            row = scheduler.register(
                condition={
                    "kind": "world_equals",
                    "path": ["environment", "period"],
                    "value": "night",
                },
                operations=[{
                    "op": "set_world",
                    "path": ["environment", "period"],
                    "value": "night",
                }],
                principal=PRINCIPAL,
            )
            initial_bytes = path.stat().st_size
            initial_lines = len(path.read_text(encoding="utf-8").splitlines())

            for tick in range(1, 101):
                result = scheduler.evaluate_tick(tick)
                self.assertEqual(result[0]["fire_count"], 0)

            self.assertEqual(path.stat().st_size, initial_bytes)
            self.assertEqual(
                len(path.read_text(encoding="utf-8").splitlines()),
                initial_lines,
            )
            self.assertEqual(
                scheduler.get(row["conditional_event_id"])["last_evaluated_tick"],
                100,
            )

    def test_condition_transition_persists_once_then_stays_sparse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conditional.jsonl"
            service = guarded()
            scheduler = ConditionalEventScheduler(path, service)
            scheduler.register(
                condition={
                    "kind": "world_equals",
                    "path": ["environment", "period"],
                    "value": "night",
                },
                operations=[{
                    "op": "set_world",
                    "path": ["environment", "period"],
                    "value": "night",
                }],
                principal=PRINCIPAL,
            )
            scheduler.evaluate_tick(1)
            service.engine.world["environment"]["period"] = "night"
            fired = scheduler.evaluate_tick(2)[0]
            self.assertEqual(fired["fire_count"], 1)
            after_fire_lines = len(path.read_text(encoding="utf-8").splitlines())

            for tick in range(3, 103):
                self.assertEqual(scheduler.evaluate_tick(tick)[0]["fire_count"], 1)

            self.assertEqual(
                len(path.read_text(encoding="utf-8").splitlines()),
                after_fire_lines,
            )

    def test_conditional_compaction_preserves_current_and_full_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "conditional.jsonl"
            rows = [
                {"conditional_event_id": "a", "status": "active", "fire_count": 0},
                {"conditional_event_id": "b", "status": "active", "fire_count": 0},
                {"conditional_event_id": "a", "status": "active", "fire_count": 1},
                {"conditional_event_id": "b", "status": "completed", "fire_count": 1},
            ]
            path.write_text(
                "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
            )
            result = compact_conditional(path)
            self.assertEqual(result["original_rows"], 4)
            self.assertEqual(result["latest_rows"], 2)
            self.assertFalse(result["history_deleted"])
            self.assertTrue((path.parent / result["archive"]).is_file())

            scheduler = ConditionalEventScheduler(path, guarded())
            current = {
                row["conditional_event_id"]: row
                for row in scheduler.current()
            }
            self.assertEqual(current["a"]["fire_count"], 1)
            self.assertEqual(current["b"]["status"], "completed")
            self.assertEqual(scheduler.history(), rows)

            again = compact_conditional(path)
            self.assertTrue(again["already_compacted"])

    def test_plan_compaction_keeps_latest_index_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            rows = [
                {
                    "plan_id": "p1",
                    "status": "planned",
                    "idempotency_key": "k1",
                    "intent": {},
                },
                {
                    "plan_id": "p2",
                    "status": "planned",
                    "idempotency_key": "k2",
                    "intent": {},
                },
                {
                    "plan_id": "p1",
                    "status": "completed",
                    "idempotency_key": "k1",
                    "intent": {"need": "explore"},
                },
                {
                    "plan_id": "p2",
                    "status": "running",
                    "idempotency_key": "k2",
                    "intent": {},
                },
            ]
            path.write_text(
                "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
            )
            result = compact_plans(path)
            self.assertEqual(result["original_rows"], 4)
            self.assertEqual(result["latest_rows"], 2)
            self.assertLess(result["compact_bytes"], result["original_bytes"])
            self.assertFalse(result["history_deleted"])

            ledger = PlanLedger(path)
            self.assertEqual(ledger.get("p1")["status"], "completed")
            self.assertEqual(ledger.get("p2")["status"], "running")
            self.assertEqual(
                ledger.get_by_idempotency_key("k1")["plan_id"],
                "p1",
            )
            self.assertEqual(
                [row["plan_id"] for row in ledger.active()],
                ["p2"],
            )
            self.assertEqual(ledger.history(), rows)

    def test_history_adds_only_post_compaction_rows_not_snapshot_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            original = [
                {"plan_id": "p1", "status": "planned", "idempotency_key": "k1"},
                {"plan_id": "p1", "status": "running", "idempotency_key": "k1"},
            ]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in original),
                encoding="utf-8",
            )
            compact_plans(path)
            appended = {
                "plan_id": "p1",
                "status": "completed",
                "idempotency_key": "k1",
            }
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(appended) + "\n")

            ledger = PlanLedger(path)
            self.assertEqual(ledger.history(), original + [appended])
            self.assertEqual(ledger.get("p1")["status"], "completed")

    def test_proposal_compaction_and_cache_preserve_lifecycle_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.jsonl"
            rows = [
                {
                    "proposal_id": "pr1",
                    "status": "proposed",
                    "idempotency_key": "k1",
                    "origin": "agent",
                    "proposer_id": "a",
                    "proposal_kind": "world_mutation",
                    "payload": {},
                },
                {
                    "proposal_id": "pr1",
                    "status": "approved",
                    "idempotency_key": "k1",
                    "origin": "agent",
                    "proposer_id": "a",
                    "proposal_kind": "world_mutation",
                    "payload": {},
                },
                {
                    "proposal_id": "pr2",
                    "status": "committed",
                    "idempotency_key": "k2",
                    "origin": "agent",
                    "proposer_id": "b",
                    "proposal_kind": "world_mutation",
                    "payload": {},
                },
            ]
            path.write_text(
                "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
            )
            result = compact_proposals(path)
            self.assertEqual(result["original_rows"], 3)
            self.assertEqual(result["latest_rows"], 2)
            ledger = ProposalLedger(path)
            self.assertEqual(ledger.get("pr1")["status"], "approved")
            self.assertEqual(ledger.get_by_idempotency_key("k2")["proposal_id"], "pr2")
            self.assertEqual(ledger.history(), rows)

            first = ledger.propose(
                origin="agent",
                proposer_id="a",
                proposal_kind="world_mutation",
                payload={"x": 1},
                idempotency_key="k1",
            )
            self.assertEqual(first["proposal_id"], "pr1")
            self.assertEqual(len(ledger.current()), 2)

    def test_rollout_compacts_only_hot_ledgers_and_requires_tick_recovery(self) -> None:
        script = (ROOT / "deploy" / "apply-hot-ledger-008d.sh").read_text(encoding="utf-8")
        self.assertIn("live-infinita-autonomous-world.service", script)
        self.assertIn("hot_ledger_compactor.py", script)
        self.assertIn("--conditional", script)
        self.assertIn("--plans", script)
        self.assertIn("--proposals", script)
        self.assertIn('assert value["history_deleted"] is False', script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("single writer não retomou avanço lógico", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)
        self.assertNotIn('rm -f "$DATA/conditional-world-events.jsonl"', script)
        self.assertNotIn('rm -f "$DATA/plans.jsonl"', script)
        self.assertNotIn('rm -f "$DATA/proposals.jsonl"', script)


if __name__ == "__main__":
    unittest.main()
