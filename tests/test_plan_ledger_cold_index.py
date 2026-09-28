from __future__ import annotations

import json
import os
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "apps" / "world-runtime"
sys.path.insert(0, str(RUNTIME))
from plan_ledger import PlanLedger, PlanLedgerError  # noqa: E402


class ColdPlanIndexTests(unittest.TestCase):
    def test_large_completed_history_keeps_only_offsets_and_one_active_payload(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plans.jsonl"
            # Large terminal payloads must remain on disk. The OOM incident
            # involved ~75k unique plans, almost all terminal.
            with path.open("wb") as fh:
                for i in range(2500):
                    row = {
                        "plan_id": f"p{i}", "status": "completed",
                        "idempotency_key": f"k{i}", "actor_entity_id": "nov",
                        "intent": {"need": "energy" if i % 5 == 0 else None},
                        "plan": {"steps": [{"payload": "x" * 4096}]},
                    }
                    fh.write((json.dumps(row) + "\n").encode())
                fh.write((json.dumps({
                    "plan_id": "active", "status": "running",
                    "actor_entity_id": "nov", "plan": {"steps": []},
                }) + "\n").encode())
            ledger = PlanLedger(path)
            tracemalloc.start()
            try:
                self.assertEqual([r["plan_id"] for r in ledger.active()], ["active"])
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(len(ledger._view_offsets), 2501)
            self.assertEqual(len(ledger._view_by_id), 1)
            self.assertEqual(len(ledger._view_need_candidates), 500)
            self.assertLess(peak, 9 * 1024 * 1024)
            self.assertEqual(ledger.get("p2499")["plan"]["steps"][0]["payload"], "x"*4096)
            self.assertEqual(ledger.get_by_idempotency_key("k100")["plan_id"], "p100")
            with patch.object(ledger, "_read_at", side_effect=AssertionError("processed cold payload read")):
                self.assertEqual(
                    ledger.pending_need_outcome_candidates({f"p{i}" for i in range(2500)}),
                    [],
                )
            self.assertEqual(
                [row["plan_id"] for row in ledger.pending_need_outcome_candidates(
                    {f"p{i}" for i in range(2499)}
                )],
                [],  # p2499 is not a need candidate
            )
            self.assertEqual(
                [row["plan_id"] for row in ledger.pending_need_outcome_candidates(
                    {f"p{i}" for i in range(2495)}
                )],
                ["p2495"],
            )

    def test_append_terminal_eviction_restore_preserves_original_order(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = PlanLedger(Path(d) / "plans.jsonl")
            ledger._append({"plan_id":"old","status":"planned","actor_entity_id":"nov"})
            ledger._append({"plan_id":"next","status":"running","actor_entity_id":"other"})
            ledger.active()
            ledger._append({"plan_id":"old","status":"completed","intent":{"need":"social"}})
            self.assertNotIn("old", ledger._view_by_id)
            self.assertIn("old", ledger._view_offsets)
            self.assertEqual([r["plan_id"] for r in ledger.pending_need_outcome_candidates(set())], ["old"])
            ledger._append({"plan_id":"old","status":"running","actor_entity_id":"nov"})
            self.assertEqual([r["plan_id"] for r in ledger.active()], ["old","next"])
            ledger._append({"plan_id":"old","status":"completed","intent":{"need":"safety"}})
            self.assertEqual([r["intent"]["need"] for r in ledger.need_outcome_candidates()], ["safety"])
            self.assertEqual(len(ledger._view_by_id), 1)
            again = PlanLedger(ledger.path)
            self.assertEqual([r["plan_id"] for r in again.current()], ["old","next"])
            self.assertEqual(again.get("old")["intent"]["need"], "safety")

    def test_index_detects_external_replacement_and_mid_record_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plans.jsonl"
            ledger = PlanLedger(path)
            ledger._append({"plan_id":"first","status":"completed"})
            self.assertEqual(ledger.get("first")["plan_id"], "first")
            repl = path.with_suffix(".replacement")
            repl.write_text(json.dumps({"plan_id":"second","status":"completed"})+"\n")
            os.replace(repl,path)
            self.assertIsNone(ledger.get("first"))
            self.assertEqual(ledger.get("second")["plan_id"], "second")
            path.write_bytes(b'{"plan_id":"a","status":"completed"}\nnot-json\n{"plan_id":"b","status":"completed"}\n')
            with self.assertRaisesRegex(PlanLedgerError, "corrupt plan ledger"):
                ledger.active()


if __name__ == "__main__":
    unittest.main()
