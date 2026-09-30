from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from plan_ledger import PlanLedger
from plan_ledger_sidecar import PlanLedgerSidecar, SCHEMA


def row(
    plan_id: str,
    status: str,
    *,
    key: str | None = None,
    need: str | None = None,
    actor: str = "nov",
) -> dict:
    intent = {"need": need} if need else {}
    return {
        "plan_id": plan_id,
        "status": status,
        "idempotency_key": key,
        "actor_entity_id": actor,
        "intent": intent,
        "plan": {"steps": [{"kind": "goal", "payload": "x" * 128}]},
    }


class PlanSidecarIndex008FTests(unittest.TestCase):
    def test_restart_uses_sidecar_without_authoritative_full_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            rows = [
                row("p1", "completed", key="k1", need="energy"),
                row("p2", "completed", key="k2"),
                row("p3", "running", key="k3"),
            ]
            path.write_text(
                "".join(json.dumps(value) + "\n" for value in rows),
                encoding="utf-8",
            )
            first = PlanLedger(path)
            stats = first.warm_index()
            first._sidecar.close(commit=True)
            self.assertEqual(stats["plans"], 3)
            self.assertTrue(path.with_name(path.name + ".index.sqlite3").is_file())

            restarted = PlanLedger(path)
            with patch.object(
                restarted,
                "_iter_rows_with_offsets",
                side_effect=AssertionError("full JSONL scan must not run"),
            ):
                self.assertEqual(
                    [value["plan_id"] for value in restarted.active()],
                    ["p3"],
                )
                self.assertEqual(
                    restarted.get_by_idempotency_key("k1")["plan_id"],
                    "p1",
                )
                self.assertEqual(
                    [value["plan_id"] for value in restarted.need_outcome_candidates()],
                    ["p1"],
                )

    def test_uncommitted_sidecar_batch_is_recovered_from_jsonl_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            path.write_text(
                json.dumps(row("base", "completed", key="base-key")) + "\n",
                encoding="utf-8",
            )
            ledger = PlanLedger(path)
            ledger.warm_index()
            ledger._append(row("tail1", "running", key="tail-k1"))
            ledger._append(row("tail2", "completed", key="tail-k2", need="social"))
            # Simulated abrupt process loss: derived transaction rolls back while
            # authoritative JSONL bytes remain durable.
            ledger._sidecar.close(commit=False)

            restarted = PlanLedger(path)
            with patch.object(
                restarted._sidecar,
                "rebuild",
                side_effect=AssertionError("tail recovery must not rebuild all rows"),
            ):
                self.assertEqual(
                    [value["plan_id"] for value in restarted.active()],
                    ["tail1"],
                )
                self.assertEqual(
                    restarted.get_by_idempotency_key("tail-k2")["plan_id"],
                    "tail2",
                )
                self.assertEqual(
                    [value["plan_id"] for value in restarted.need_outcome_candidates()],
                    ["tail2"],
                )

    def test_external_append_applies_only_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            path.write_text(
                json.dumps(row("p1", "completed", key="k1")) + "\n",
                encoding="utf-8",
            )
            initial = PlanLedger(path)
            initial.warm_index()
            initial._sidecar.close(commit=True)

            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row("p2", "running", key="k2")) + "\n")

            restarted = PlanLedger(path)
            with patch.object(
                restarted._sidecar,
                "rebuild",
                side_effect=AssertionError("append-only tail must be incremental"),
            ):
                self.assertEqual(
                    [value["plan_id"] for value in restarted.active()],
                    ["p2"],
                )
                self.assertEqual(
                    restarted.get_by_idempotency_key("k1")["plan_id"],
                    "p1",
                )

    def test_sidecar_contains_metadata_only_not_plan_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            secret_payload = "payload-not-in-derived-index-" + ("z" * 2000)
            value = row("p1", "completed", key="k1")
            value["plan"]["steps"][0]["payload"] = secret_payload
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            ledger = PlanLedger(path)
            ledger.warm_index()
            ledger._sidecar.flush()
            ledger._sidecar.close(commit=True)

            index_path = path.with_name(path.name + ".index.sqlite3")
            self.assertNotIn(secret_payload.encode(), index_path.read_bytes())
            sidecar = PlanLedgerSidecar(path)
            try:
                self.assertEqual(sidecar._meta("schema"), SCHEMA)
                materialized = sidecar.materialized_rows()
                self.assertEqual(materialized[0][0], "p1")
                self.assertEqual(materialized[0][3], "k1")
            finally:
                sidecar.close(commit=False)

    def test_prefix_rewrite_invalidates_sidecar_and_preserves_corruption_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plans.jsonl"
            path.write_text(
                json.dumps(row("p1", "completed")) + "\n",
                encoding="utf-8",
            )
            ledger = PlanLedger(path)
            ledger.warm_index()
            ledger._sidecar.close(commit=True)

            path.write_bytes(
                b'{"plan_id":"a","status":"completed"}\n'
                b'not-json\n'
                b'{"plan_id":"b","status":"completed"}\n'
            )
            restarted = PlanLedger(path)
            with self.assertRaisesRegex(ValueError, "corrupt plan ledger"):
                restarted.active()

    def test_source_contract_warms_before_tick_driver(self) -> None:
        source = (RUNTIME / "autonomous_runtime.py").read_text(encoding="utf-8")
        ledger = (RUNTIME / "plan_ledger.py").read_text(encoding="utf-8")
        self.assertIn("plans.warm_index()", source)
        self.assertIn("PlanLedgerSidecar", ledger)
        self.assertIn("note_append(", ledger)

    def test_rollout_builds_sidecar_with_writer_stopped_and_requires_tick_recovery(self) -> None:
        script = (ROOT / "deploy" / "apply-plan-sidecar-index-008f.sh").read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("plan_ledger_sidecar.py", script)
        self.assertIn("--rebuild", script)
        self.assertIn("runuser -u liveinfinita", script)
        self.assertIn("indexed_size", script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("LIVE_INFINITA_WORLD_BUILDER=1", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)
        self.assertNotIn('rm -f "$DATA/plans.jsonl"', script)


if __name__ == "__main__":
    unittest.main()
