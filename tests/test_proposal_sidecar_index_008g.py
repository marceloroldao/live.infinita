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

from proposal_ledger import ProposalLedger
from proposal_ledger_bridge import ProposalLedgerBridge
from proposal_ledger_sidecar import ProposalLedgerSidecar, SCHEMA


def proposal_row(
    proposal_id: str,
    status: str,
    *,
    key: str | None = None,
    origin: str = "agent",
    source_id: str | None = None,
    payload: str = "x",
) -> dict:
    return {
        "proposal_schema": "proposal_ledger_v1",
        "proposal_id": proposal_id,
        "source_proposal_id": source_id,
        "origin": origin,
        "proposer_id": "tester",
        "proposal_kind": "agent_intent",
        "status": status,
        "payload": {"value": payload},
        "metadata": {},
        "idempotency_key": key,
    }


class ProposalSidecar008GTests(unittest.TestCase):
    def test_restart_uses_sidecar_without_jsonl_full_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.jsonl"
            rows = [
                proposal_row("p1", "committed", key="k1", origin="ai", source_id="a1"),
                proposal_row("p2", "rejected", key="k2"),
                proposal_row("p3", "approved", key="k3"),
            ]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            first = ProposalLedger(path)
            stats = first.warm_index()
            first._sidecar.close(commit=True)
            self.assertEqual(stats["proposals"], 3)

            restarted = ProposalLedger(path)
            with patch.object(
                restarted,
                "_iter_rows_with_offsets",
                side_effect=AssertionError("full proposal replay must not run"),
            ):
                self.assertEqual(restarted.get("p3")["status"], "approved")
                self.assertEqual(
                    restarted.get_by_idempotency_key("k1")["proposal_id"],
                    "p1",
                )
                self.assertEqual(
                    restarted.get_by_source("ai", "a1")["proposal_id"],
                    "p1",
                )
                self.assertEqual(
                    [row["proposal_id"] for row in restarted.current()],
                    ["p1", "p2", "p3"],
                )

    def test_uncommitted_sidecar_batch_recovers_from_jsonl_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.jsonl"
            path.write_text(
                json.dumps(proposal_row("base", "committed", key="base")) + "\n",
                encoding="utf-8",
            )
            ledger = ProposalLedger(path)
            ledger.warm_index()
            ledger._append(
                proposal_row(
                    "tail1", "proposed", key="tail-k1",
                    origin="audience", source_id="aud-1",
                )
            )
            ledger._append(
                proposal_row("tail2", "approved", key="tail-k2")
            )
            # Simulated abrupt process loss: JSONL fsync is authoritative; the
            # derived SQLite batch is allowed to roll back.
            ledger._sidecar.close(commit=False)

            restarted = ProposalLedger(path)
            with patch.object(
                restarted._sidecar,
                "rebuild",
                side_effect=AssertionError("small tail must not rebuild prefix"),
            ):
                self.assertEqual(
                    restarted.get_by_idempotency_key("tail-k2")["proposal_id"],
                    "tail2",
                )
                self.assertEqual(
                    restarted.get_by_source("audience", "aud-1")["proposal_id"],
                    "tail1",
                )

    def test_external_append_applies_only_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.jsonl"
            path.write_text(
                json.dumps(proposal_row("p1", "committed", key="k1")) + "\n",
                encoding="utf-8",
            )
            first = ProposalLedger(path)
            first.warm_index()
            first._sidecar.close(commit=True)

            with path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        proposal_row("p2", "proposed", key="k2")
                    ) + "\n"
                )

            restarted = ProposalLedger(path)
            with patch.object(
                restarted._sidecar,
                "rebuild",
                side_effect=AssertionError("append-only tail must be incremental"),
            ):
                self.assertEqual(restarted.get("p2")["status"], "proposed")
                self.assertEqual(
                    restarted.get_by_idempotency_key("k1")["proposal_id"],
                    "p1",
                )

    def test_bridge_source_lookup_does_not_materialize_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ProposalLedger(Path(tmp) / "proposals.jsonl")
            bridge = ProposalLedgerBridge(ledger)
            mirrored = bridge.mirror_audience({
                "proposal_id": "aud-9",
                "gateway_text": "fogueira",
                "rule_id": "likes",
            })
            with patch.object(
                ledger,
                "current",
                side_effect=AssertionError("bridge source lookup used current()"),
            ):
                found = bridge._find("audience", "aud-9")
            self.assertEqual(found["proposal_id"], mirrored["proposal_id"])

    def test_sidecar_never_contains_proposal_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.jsonl"
            secret = "proposal-payload-must-stay-jsonl-" + ("q" * 4096)
            path.write_text(
                json.dumps(
                    proposal_row(
                        "p1", "committed", key="k1", payload=secret
                    )
                ) + "\n",
                encoding="utf-8",
            )
            ledger = ProposalLedger(path)
            ledger.warm_index()
            ledger._sidecar.flush()
            ledger._sidecar.close(commit=True)

            index_path = path.with_name(path.name + ".index.sqlite3")
            self.assertNotIn(secret.encode(), index_path.read_bytes())
            sidecar = ProposalLedgerSidecar(path)
            try:
                self.assertEqual(sidecar._meta("schema"), SCHEMA)
                self.assertEqual(
                    sidecar.materialized_rows()[0][0],
                    "p1",
                )
            finally:
                sidecar.close(commit=False)

    def test_prefix_rewrite_invalidates_index_and_keeps_corruption_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposals.jsonl"
            path.write_text(
                json.dumps(proposal_row("p1", "committed")) + "\n",
                encoding="utf-8",
            )
            ledger = ProposalLedger(path)
            ledger.warm_index()
            ledger._sidecar.close(commit=True)

            path.write_bytes(
                b'{"proposal_id":"a","status":"committed"}\n'
                b'not-json\n'
                b'{"proposal_id":"b","status":"committed"}\n'
            )
            restarted = ProposalLedger(path)
            with self.assertRaisesRegex(ValueError, "corrupt proposal ledger"):
                restarted.get("a")

    def test_source_contract_warms_proposals_before_tick_runtime(self) -> None:
        source = (RUNTIME / "autonomous_runtime.py").read_text(encoding="utf-8")
        ledger = (RUNTIME / "proposal_ledger.py").read_text(encoding="utf-8")
        bridge = (RUNTIME / "proposal_ledger_bridge.py").read_text(encoding="utf-8")
        self.assertIn("proposals.warm_index()", source)
        self.assertIn("ProposalLedgerSidecar", ledger)
        self.assertIn("note_append(", ledger)
        self.assertIn("get_by_source", bridge)

    def test_rollout_builds_index_with_single_writer_stopped(self) -> None:
        script = (
            ROOT / "deploy" / "apply-proposal-sidecar-index-008g.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("proposal_ledger_sidecar.py", script)
        self.assertIn("--rebuild", script)
        self.assertIn("runuser -u liveinfinita", script)
        self.assertIn("indexed_size", script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("LIVE_INFINITA_WORLD_BUILDER=1", script)
        self.assertIn("plans.jsonl.index.sqlite3", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)
        self.assertNotIn('rm -f "$DATA/proposals.jsonl"', script)


if __name__ == "__main__":
    unittest.main()
