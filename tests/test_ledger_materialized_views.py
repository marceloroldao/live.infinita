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


if __name__ == "__main__":
    unittest.main()
