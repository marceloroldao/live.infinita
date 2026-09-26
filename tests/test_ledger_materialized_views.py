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


if __name__ == "__main__":
    unittest.main()
