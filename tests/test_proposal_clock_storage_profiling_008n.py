from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from proposal_ledger import ProposalLedger
from simulation_clock import SimulationClock


class ProposalClockStorageProfiling008NTests(unittest.TestCase):
    def test_proposal_append_reports_write_fsync_and_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observed: list[tuple[str, int]] = []
            ledger = ProposalLedger(
                Path(tmpdir) / "proposals.jsonl",
                stage_observer=lambda name, elapsed: observed.append(
                    (name, elapsed)
                ),
            )
            row = ledger.propose(
                origin="agent",
                proposer_id="agent-1",
                proposal_kind="agent_intent",
                payload={"intent": {"intent": "move_to_position"}},
            )
            self.assertEqual(row["status"], "proposed")
            names = [name for name, _ in observed]
            self.assertIn("proposal.ledger.append.write", names)
            self.assertIn("proposal.ledger.append.fsync", names)
            self.assertIn("proposal.ledger.append.sidecar", names)
            self.assertTrue(all(elapsed >= 0 for _, elapsed in observed))

    def test_proposal_pair_reports_single_pair_fsync(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observed: list[tuple[str, int]] = []
            ledger = ProposalLedger(
                Path(tmpdir) / "proposals.jsonl",
                stage_observer=lambda name, elapsed: observed.append(
                    (name, elapsed)
                ),
            )
            row = ledger.propose_approved(
                origin="npc_need",
                proposer_id="npc:nov",
                proposal_kind="agent_intent",
                payload={"intent": {"intent": "move_to_position"}},
                decided_by="need_policy:energy",
                idempotency_key="need:nov:energy:1",
            )
            self.assertEqual(row["status"], "approved")
            names = [name for name, _ in observed]
            self.assertEqual(names.count("proposal.ledger.pair.fsync"), 1)
            self.assertIn("proposal.ledger.pair.write", names)
            self.assertIn("proposal.ledger.pair.sidecar", names)
            self.assertNotIn("proposal.ledger.append.fsync", names)

    def test_proposal_observer_failure_is_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = ProposalLedger(
                Path(tmpdir) / "proposals.jsonl",
                stage_observer=lambda *_: (_ for _ in ()).throw(
                    RuntimeError("observer unavailable")
                ),
            )
            row = ledger.propose(
                origin="agent",
                proposer_id="agent-1",
                proposal_kind="agent_intent",
                payload={"intent": {"intent": "move_to_position"}},
            )
            self.assertEqual(row["status"], "proposed")
            self.assertEqual(ledger.current()[0]["proposal_id"], row["proposal_id"])

    def test_clock_reports_read_write_and_replace_without_semantic_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            observed: list[tuple[str, int]] = []
            clock = SimulationClock(
                Path(tmpdir) / "clock.json",
                tick_duration_ms=500,
                stage_observer=lambda name, elapsed: observed.append(
                    (name, elapsed)
                ),
            )
            observed.clear()
            state = clock.advance()
            self.assertEqual(state.tick, 1)
            names = [name for name, _ in observed]
            self.assertIn("clock.storage.read", names)
            self.assertIn("clock.storage.parse", names)
            self.assertIn("clock.storage.serialize", names)
            self.assertIn("clock.storage.write_tmp", names)
            self.assertIn("clock.storage.replace", names)
            self.assertEqual(SimulationClock(clock.path).state().tick, 1)

    def test_clock_observer_failure_is_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clock = SimulationClock(
                Path(tmpdir) / "clock.json",
                stage_observer=lambda *_: (_ for _ in ()).throw(
                    RuntimeError("observer unavailable")
                ),
            )
            self.assertEqual(clock.advance().tick, 1)
            self.assertEqual(SimulationClock(clock.path).state().tick, 1)

    def test_profiler_wires_proposal_ledger_and_clock(self) -> None:
        source = (RUNTIME / "tick_driver_main.py").read_text(encoding="utf-8")
        self.assertIn(
            'proposal_ledger = getattr(scheduler, "proposal_ledger", None)',
            source,
        )
        self.assertIn(
            "proposal_ledger.stage_observer = profiler.observe_stage",
            source,
        )
        self.assertIn(
            'clock = getattr(authoritative, "clock", None)',
            source,
        )
        self.assertIn(
            "clock.stage_observer = profiler.observe_stage",
            source,
        )

    def test_source_contract_keeps_persistence_primitives(self) -> None:
        proposal = (RUNTIME / "proposal_ledger.py").read_text(encoding="utf-8")
        clock = (RUNTIME / "simulation_clock.py").read_text(encoding="utf-8")
        self.assertIn("os.fsync(fd)", proposal)
        self.assertIn("proposal.ledger.append.fsync", proposal)
        self.assertIn("proposal.ledger.pair.fsync", proposal)
        self.assertIn("tmp.replace(self.path)", clock)
        self.assertIn("clock.storage.write_tmp", clock)
        self.assertIn("clock.storage.replace", clock)


if __name__ == "__main__":
    unittest.main()
