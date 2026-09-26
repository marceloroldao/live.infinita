from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WORLD_RUNTIME = Path(__file__).resolve().parents[1] / "apps" / "world-runtime"
sys.path.insert(0, str(WORLD_RUNTIME))

from plan_ledger import PlanLedger, PlanLedgerError


def _valid_row(plan_id: str) -> bytes:
    return (json.dumps({"plan_id": plan_id, "status": "planned"}) + "\n").encode()


class PlanLedgerCrashSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_history_recovers_only_torn_final_record(self) -> None:
        path = self.root / "plans.jsonl"
        good = _valid_row("p1")
        torn = b'{"plan_id":"p2","status":'
        path.write_bytes(good + torn)
        ledger = PlanLedger(path)

        self.assertEqual(ledger.history(), [{"plan_id": "p1", "status": "planned"}])
        self.assertEqual(path.read_bytes(), good)
        self.assertEqual((self.root / "plans.jsonl.torn-tail").read_bytes(), torn)

    def test_history_recovers_nul_tail_seen_in_production(self) -> None:
        path = self.root / "plans.jsonl"
        good = _valid_row("p1")
        path.write_bytes(good + (b"\x00" * 940))

        self.assertEqual(PlanLedger(path).history(), [{"plan_id": "p1", "status": "planned"}])
        self.assertEqual(path.read_bytes(), good)
        self.assertEqual((self.root / "plans.jsonl.torn-tail").read_bytes(), b"\x00" * 940)

    def test_history_refuses_corruption_in_middle(self) -> None:
        path = self.root / "plans.jsonl"
        path.write_bytes(_valid_row("p1") + b"not-json\n" + _valid_row("p2"))
        with self.assertRaisesRegex(PlanLedgerError, "corrupt plan ledger"):
            PlanLedger(path).history()
        self.assertTrue(path.read_bytes().endswith(_valid_row("p2")))
        self.assertFalse((self.root / "plans.jsonl.torn-tail").exists())

    def test_append_is_durable_and_jsonl_valid(self) -> None:
        path = self.root / "plans.jsonl"
        ledger = PlanLedger(path)
        row = {"plan_id": "p1", "status": "planned", "text": "ação"}
        self.assertEqual(ledger._append(row), row)
        self.assertTrue(path.read_bytes().endswith(b"\n"))
        self.assertEqual(ledger.history(), [row])


if __name__ == "__main__":
    unittest.main()
