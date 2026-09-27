from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WORLD_RUNTIME = Path(__file__).resolve().parents[1] / "apps" / "world-runtime"
sys.path.insert(0, str(WORLD_RUNTIME))

from conditional_event_scheduler import ConditionalEventScheduler
from plan_ledger import PlanLedger
from npc_strategy_executor import NpcStrategyExecutor


def _row(kind: str, identity: str, status: str = "planned") -> dict:
    return {kind: identity, "status": status, "nested": {"count": 1}}


def _encoded(row: dict) -> bytes:
    return (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")


class MaterializedLedgerViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_plan_view_avoids_replay_after_append_and_preserves_detachment(self) -> None:
        ledger = PlanLedger(self.root / "plans.jsonl")
        initial = _row("plan_id", "one")
        ledger._append(initial)
        with patch.object(ledger, "history", wraps=ledger.history) as replay:
            self.assertEqual(ledger.get("one"), initial)
            self.assertEqual(replay.call_count, 1)
            ledger._append(_row("plan_id", "two", "running"))
            ledger._append(_row("plan_id", "one", "completed"))
            self.assertEqual(ledger.get("one")["status"], "completed")
            self.assertEqual([r["plan_id"] for r in ledger.active()], ["two"])
            self.assertEqual([r["plan_id"] for r in ledger.current()], ["one", "two"])
            self.assertEqual(replay.call_count, 1)
            returned = ledger.get("one")
            returned["nested"]["count"] = 999
            self.assertEqual(ledger.get("one")["nested"]["count"], 1)
            self.assertEqual(len(ledger.history()), 3)

    def test_plan_view_detects_external_append_and_atomic_replacement(self) -> None:
        path = self.root / "plans.jsonl"
        ledger = PlanLedger(path)
        ledger._append(_row("plan_id", "one"))
        self.assertEqual(len(ledger.current()), 1)
        with path.open("ab") as fh:
            fh.write(_encoded(_row("plan_id", "two")))
        self.assertEqual([r["plan_id"] for r in ledger.current()], ["one", "two"])
        replacement = self.root / "replacement.jsonl"
        replacement.write_bytes(_encoded(_row("plan_id", "three")))
        os.replace(replacement, path)
        self.assertEqual([r["plan_id"] for r in ledger.current()], ["three"])

    def test_conditional_view_avoids_full_replay_and_detects_external_append(self) -> None:
        path = self.root / "conditions.jsonl"
        ledger = ConditionalEventScheduler(path, None)
        key = "conditional_event_id"
        ledger._append(_row(key, "one", "active"))
        with patch.object(ledger, "_iter_history", wraps=ledger._iter_history) as replay:
            self.assertEqual(ledger.get("one")["status"], "active")
            self.assertEqual(replay.call_count, 1)
            ledger._append(_row(key, "one", "completed"))
            ledger._append(_row(key, "two", "active"))
            self.assertEqual([r[key] for r in ledger.current()], ["one", "two"])
            self.assertEqual(replay.call_count, 1)
            returned = ledger.get("two")
            returned["nested"]["count"] = 999
            self.assertEqual(ledger.get("two")["nested"]["count"], 1)
            with path.open("ab") as fh:
                fh.write(_encoded(_row(key, "three", "active")))
            self.assertEqual([r[key] for r in ledger.current()], ["one", "two", "three"])
            self.assertEqual(replay.call_count, 2)
            replacement = self.root / "replacement.jsonl"
            replacement.write_bytes(_encoded(_row(key, "four", "active")))
            os.replace(replacement, path)
            self.assertEqual([r[key] for r in ledger.current()], ["four"])
            self.assertEqual(replay.call_count, 3)


    def test_plan_idempotency_uses_index_and_preserves_existing_latest_record(self) -> None:
        ledger = PlanLedger(self.root / "plans.jsonl")
        ledger._append({"plan_id": "one", "idempotency_key": "repeat", "status": "planned"})
        self.assertEqual(ledger.get_by_idempotency_key("repeat")["plan_id"], "one")
        with patch.object(ledger, "current", side_effect=AssertionError("full scan")):
            existing = ledger.create(
                proposal_id=None, proposer_id="tester", principal={}, intent={},
                plan={}, idempotency_key="repeat",
            )
        self.assertEqual(existing["plan_id"], "one")
        ledger._append({"plan_id": "one", "idempotency_key": "repeat", "status": "completed"})
        self.assertEqual(ledger.get_by_idempotency_key("repeat")["status"], "completed")
        self.assertIsNone(ledger.get_by_idempotency_key("missing"))
        with (self.root / "plans.jsonl").open("ab") as fh:
            fh.write(_encoded({"plan_id": "two", "idempotency_key": "external", "status": "planned"}))
        self.assertEqual(ledger.get_by_idempotency_key("external")["plan_id"], "two")

    def test_strategy_executor_index_avoids_replays_for_per_execution_lookup(self) -> None:
        path = self.root / "strategy.jsonl"
        executor = NpcStrategyExecutor(path, None)
        plan = {"phases": [{"kind": "wait_ticks", "intent": {"ticks": 1}}]}
        first = executor.start(plan, principal={}, proposer_id="test", idempotency_key="repeat")
        with patch.object(executor, "_history", wraps=executor._history) as replay:
            self.assertEqual(executor.get(first["strategy_execution_id"]), first)
            self.assertEqual(replay.call_count, 0)
            with patch.object(executor, "current", side_effect=AssertionError("full scan")):
                self.assertEqual(
                    executor.start(plan, principal={}, proposer_id="test", idempotency_key="repeat"),
                    first,
                )
            updated = executor._update(first, phase_index=1)
            self.assertEqual(executor.get(first["strategy_execution_id"]), updated)
            self.assertEqual(replay.call_count, 0)
            self.assertEqual(executor.get_by_idempotency_key("repeat"), updated)
            external = {"strategy_execution_id": "external", "idempotency_key": "other", "status": "running"}
            with path.open("ab") as fh:
                fh.write(_encoded(external))
            self.assertEqual(executor.get("external"), external)
            self.assertEqual(replay.call_count, 1)
            replacement = self.root / "other-strategy.jsonl"
            replacement.write_bytes(_encoded({"strategy_execution_id": "replacement", "status": "completed"}))
            os.replace(replacement, path)
            self.assertEqual([x["strategy_execution_id"] for x in executor.current()], ["replacement"])
            self.assertEqual(replay.call_count, 2)


    def test_completed_need_candidate_index_keeps_creation_order_without_full_current_copy(self) -> None:
        path = self.root / "plans.jsonl"
        ledger = PlanLedger(path)
        ledger._append({"plan_id": "older", "status": "planned", "intent": {"need": "energy"}})
        ledger._append({"plan_id": "newer", "status": "completed", "intent": {"need": "social"}})
        ledger._append({"plan_id": "excluded", "status": "completed", "intent": {"need": "safety", "need_outcome_eligible": False}})
        ledger._append({"plan_id": "irrelevant", "status": "completed", "intent": {}})
        with patch.object(ledger, "current", side_effect=AssertionError("must not copy full ledger")):
            self.assertEqual([r["plan_id"] for r in ledger.need_outcome_candidates()], ["newer"])
            ledger._append({"plan_id": "older", "status": "completed", "intent": {"need": "energy"}})
            self.assertEqual([r["plan_id"] for r in ledger.need_outcome_candidates()], ["older", "newer"])
            detached = ledger.need_outcome_candidates()
            detached[0]["intent"]["need"] = "changed"
            self.assertEqual(ledger.need_outcome_candidates()[0]["intent"]["need"], "energy")
            with path.open("ab") as fh:
                fh.write(_encoded({"plan_id": "external", "status": "completed", "intent": {"need": "curiosity"}}))
            self.assertEqual([r["plan_id"] for r in ledger.need_outcome_candidates()], ["older", "newer", "external"])
            replacement = self.root / "replacement-plans.jsonl"
            replacement.write_bytes(_encoded({"plan_id": "replacement", "status": "completed", "intent": {"need": "safety"}}))
            os.replace(replacement, path)
            self.assertEqual([r["plan_id"] for r in ledger.need_outcome_candidates()], ["replacement"])


    def test_strategy_completed_and_ongoing_queries_skip_full_snapshot_copy(self) -> None:
        path = self.root / "strategy.jsonl"
        executor = NpcStrategyExecutor(path, None)
        rows = [
            {"strategy_execution_id": "done1", "status": "completed", "strategy_plan": {"actor_entity_id": "nov", "need": "safety"}},
            {"strategy_execution_id": "running", "status": "running", "strategy_plan": {"actor_entity_id": "nov", "need": "social"}},
            {"strategy_execution_id": "done2", "status": "completed", "strategy_plan": {"actor_entity_id": "nov", "need": "energy"}},
        ]
        for row in rows:
            executor._append(row)
        with patch.object(executor, "current", side_effect=AssertionError("full current copied")):
            self.assertEqual([x["strategy_execution_id"] for x in executor.unprocessed_completed({"done1"})], ["done2"])
            active = executor.ongoing_for_need("nov", "social")
            self.assertEqual(active["strategy_execution_id"], "running")
            active["strategy_plan"]["need"] = "corrupted"
            self.assertEqual(executor.ongoing_for_need("nov", "social")["strategy_plan"]["need"], "social")
            self.assertIsNone(executor.ongoing_for_need("nov", "safety"))
            with path.open("ab") as fh:
                fh.write(_encoded({"strategy_execution_id": "external", "status": "completed", "strategy_plan": {"actor_entity_id": "nov", "need": "curiosity"}}))
            self.assertEqual([x["strategy_execution_id"] for x in executor.unprocessed_completed({"done1"})], ["done2", "external"])
            replacement = self.root / "replacement-strategy.jsonl"
            replacement.write_bytes(_encoded({"strategy_execution_id": "replacement", "status": "completed"}))
            os.replace(replacement, path)
            self.assertEqual([x["strategy_execution_id"] for x in executor.unprocessed_completed(set())], ["replacement"])


    def test_pending_need_candidates_exclude_processed_without_copy_and_reconcile_changes(self) -> None:
        path = self.root / "plans.jsonl"
        ledger = PlanLedger(path)
        def completed(identifier):
            return {"plan_id": identifier, "status": "completed", "intent": {"need": "energy"}, "nested": {"value": 1}}
        ledger._append(completed("old"))
        ledger._append(completed("new"))
        with patch.object(ledger, "current", side_effect=AssertionError("full history copied")):
            with patch("plan_ledger.deepcopy", side_effect=AssertionError("no deepcopy of processed plans")):
                self.assertEqual(ledger.pending_need_outcome_candidates({"old", "new"}), [])
            self.assertEqual([r["plan_id"] for r in ledger.pending_need_outcome_candidates({"old"})], ["new"])
            detached = ledger.pending_need_outcome_candidates({"old"})
            detached[0]["nested"]["value"] = 99
            self.assertEqual(ledger.pending_need_outcome_candidates({"old"})[0]["nested"]["value"], 1)
            ledger._append(completed("third"))
            self.assertEqual([r["plan_id"] for r in ledger.pending_need_outcome_candidates({"old", "new"})], ["third"])
            with path.open("ab") as fh:
                fh.write(_encoded(completed("external")))
            self.assertEqual([r["plan_id"] for r in ledger.pending_need_outcome_candidates({"old", "new"})], ["third", "external"])
            replacement = self.root / "replace-pending.jsonl"
            replacement.write_bytes(_encoded(completed("replacement")))
            os.replace(replacement, path)
            self.assertEqual([r["plan_id"] for r in ledger.pending_need_outcome_candidates({"old"})], ["replacement"])


    def test_active_plan_index_matches_original_order_and_is_detached(self) -> None:
        path = self.root / "active-plans.jsonl"
        ledger = PlanLedger(path)
        for plan_id, status, actor in (
            ("old", "planned", "nov"),
            ("other", "running", "someone"),
            ("done", "completed", "nov"),
            ("late", "waiting", "nov"),
        ):
            ledger._append({
                "plan_id": plan_id, "status": status,
                "actor_entity_id": actor, "nested": {"count": 1},
            })
        self.assertEqual([r["plan_id"] for r in ledger.active()], ["old", "other", "late"])
        with patch.object(ledger, "history", side_effect=AssertionError("unexpected replay")):
            with patch.object(ledger, "current", side_effect=AssertionError("all history copied")):
                self.assertTrue(ledger.has_active_plan_for_actor("nov"))
                self.assertFalse(ledger.has_active_plan_for_actor("missing"))
                ledger._append({
                    "plan_id": "old", "status": "waiting",
                    "actor_entity_id": "nov", "nested": {"count": 2},
                })
                self.assertEqual([r["plan_id"] for r in ledger.active()], ["old", "other", "late"])
                ledger._append({
                    "plan_id": "old", "status": "completed",
                    "actor_entity_id": "nov", "nested": {"count": 3},
                })
                self.assertEqual([r["plan_id"] for r in ledger.active()], ["other", "late"])
                detached = ledger.active()
                detached[0]["nested"]["count"] = 999
                self.assertEqual(ledger.active()[0]["nested"]["count"], 1)
                ledger._append({
                    "plan_id": "new", "status": "planned",
                    "actor_entity_id": "nov", "nested": {"count": 4},
                })
                self.assertEqual([r["plan_id"] for r in ledger.active()], ["other", "late", "new"])
                self.assertTrue(ledger.has_active_plan_for_actor("nov"))
                # An unusual raw restoration must not reorder the old ID.
                ledger._append({
                    "plan_id": "old", "status": "running",
                    "actor_entity_id": "nov", "nested": {"count": 5},
                })
                self.assertEqual(
                    [r["plan_id"] for r in ledger.active()],
                    ["old", "other", "late", "new"],
                )

    def test_active_plan_index_rebuilds_on_external_append_and_replacement(self) -> None:
        path = self.root / "active-external.jsonl"
        ledger = PlanLedger(path)
        ledger._append({"plan_id": "old", "status": "planned", "actor_entity_id": "nov"})
        self.assertTrue(ledger.has_active_plan_for_actor("nov"))
        with path.open("ab") as fh:
            fh.write(_encoded({"plan_id": "old", "status": "completed", "actor_entity_id": "nov"}))
            fh.write(_encoded({"plan_id": "external", "status": "running", "actor_entity_id": "guest"}))
        self.assertFalse(ledger.has_active_plan_for_actor("nov"))
        self.assertEqual([r["plan_id"] for r in ledger.active()], ["external"])
        replacement = self.root / "replacement-active.jsonl"
        replacement.write_bytes(
            _encoded({"plan_id": "replacement", "status": "waiting", "actor_entity_id": "nov"})
        )
        os.replace(replacement, path)
        self.assertEqual([r["plan_id"] for r in ledger.active()], ["replacement"])
        self.assertTrue(ledger.has_active_plan_for_actor("nov"))
        self.assertFalse(ledger.has_active_plan_for_actor("guest"))

    def test_active_view_does_not_scan_historical_id_order_or_copy_for_membership(self) -> None:
        path = self.root / "active-large.jsonl"
        rows = [
            {"plan_id": f"terminal-{i}", "status": "completed", "actor_entity_id": "nov"}
            for i in range(2000)
        ]
        rows.extend([
            {"plan_id": "live-other", "status": "running", "actor_entity_id": "other"},
            {"plan_id": "live-nov", "status": "waiting", "actor_entity_id": "nov"},
        ])
        path.write_bytes(b"".join(_encoded(row) for row in rows))
        ledger = PlanLedger(path)
        self.assertEqual([r["plan_id"] for r in ledger.active()], ["live-other", "live-nov"])
        class ForbiddenOrder:
            def __iter__(self):
                raise AssertionError("active query scanned full historical order")

        with patch.object(ledger, "_view_order", ForbiddenOrder()):
            with patch("plan_ledger.deepcopy", side_effect=AssertionError("membership copied payload")):
                self.assertTrue(ledger.has_active_plan_for_actor("nov"))
                self.assertFalse(ledger.has_active_plan_for_actor("unknown"))
            self.assertEqual([r["plan_id"] for r in ledger.active()], ["live-other", "live-nov"])


if __name__ == "__main__":
    unittest.main()
