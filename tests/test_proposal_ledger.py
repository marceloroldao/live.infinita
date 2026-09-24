from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, RUNTIME / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ledger_module = load("proposal_ledger_test_module", "proposal_ledger.py")
bridge_module = load("proposal_ledger_bridge_test_module", "proposal_ledger_bridge.py")
ProposalLedger = ledger_module.ProposalLedger
ProposalLedgerError = ledger_module.ProposalLedgerError
ProposalLedgerBridge = bridge_module.ProposalLedgerBridge


class ProposalLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = ProposalLedger(Path(self.tmp.name) / "proposal-ledger.jsonl")
        self.bridge = ProposalLedgerBridge(self.ledger)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lifecycle_requires_approval_before_commit(self) -> None:
        proposal = self.ledger.propose(
            origin="agent",
            proposer_id="agent-1",
            proposal_kind="world_mutation",
            payload={"operations": [{"op": "move", "entity_id": "nov", "position": {"x": 1, "y": 2}}]},
        )
        with self.assertRaises(ProposalLedgerError):
            self.ledger.commit(
                proposal["proposal_id"],
                decided_by="operator",
                mutation_decision_id="md_1",
                world_event_id="evt_1",
            )
        approved = self.ledger.approve(proposal["proposal_id"], decided_by="operator")
        self.assertEqual(approved["status"], "approved")
        committed = self.ledger.commit(
            proposal["proposal_id"],
            decided_by="operator",
            mutation_decision_id="md_1",
            world_event_id="evt_1",
        )
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(committed["mutation_decision_id"], "md_1")
        self.assertEqual(committed["world_event_id"], "evt_1")

    def test_terminal_states_cannot_transition(self) -> None:
        proposal = self.ledger.propose(
            origin="audience", proposer_id="audience", proposal_kind="world_mutation", payload={"action": "toggle_fire"}
        )
        rejected = self.ledger.reject(proposal["proposal_id"], decided_by="operator", reason="not now")
        self.assertEqual(rejected["status"], "rejected")
        with self.assertRaises(ProposalLedgerError):
            self.ledger.approve(proposal["proposal_id"], decided_by="operator")

    def test_idempotency_prevents_duplicate_mirroring(self) -> None:
        legacy = {"proposal_id": "ai-1", "actor_id": "router", "action": "toggle_fire", "confidence": 0.9, "reason": "test", "model": "x", "gateway_text": "fogueira", "metadata": {}}
        first = self.bridge.mirror_ai(legacy)
        second = self.bridge.mirror_ai(legacy)
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(len(self.ledger.current()), 1)

    def test_bridge_links_legacy_proposal_to_mutation_decision_and_world_event(self) -> None:
        legacy = {"proposal_id": "aud-1", "gateway_text": "fogueira", "rule_id": "likes-50", "reason": "threshold"}
        mirrored = self.bridge.mirror_audience(legacy)
        self.assertEqual(mirrored["status"], "proposed")
        committed = self.bridge.commit_by_source(
            "audience",
            "aud-1",
            decided_by="operator",
            mutation_decision_id="md_abc",
            world_event_id="evt_123",
        )
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(committed["mutation_decision_id"], "md_abc")
        self.assertEqual(committed["world_event_id"], "evt_123")

    def test_expiration_is_terminal(self) -> None:
        proposal = self.ledger.propose(
            origin="memory", proposer_id="memoria.ia", proposal_kind="world_mutation", payload={"operations": []}
        )
        expired = self.ledger.expire(proposal["proposal_id"], reason="ttl")
        self.assertEqual(expired["status"], "expired")
        with self.assertRaises(ProposalLedgerError):
            self.ledger.reject(proposal["proposal_id"], decided_by="operator", reason="late")


if __name__ == "__main__":
    unittest.main()
