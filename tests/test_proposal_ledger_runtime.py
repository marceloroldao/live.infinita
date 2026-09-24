from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
AI_DIR = ROOT / "apps" / "ai"
for path in (RUNTIME, AI_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from proposals import AIProposalStore
from mutation_decision_log import MutationDecisionLog
from proposal_ledger import ProposalLedger
from proposal_ledger_bridge import ProposalLedgerBridge
from proposal_ledger_runtime import DualWriteAIProposalStore, AudienceProposalAppendMirror


class ProposalLedgerRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.ai_file = root / "ai-proposals.jsonl"
        self.audience_file = root / "audience-proposals.jsonl"
        self.ledger = ProposalLedger(root / "proposal-ledger.jsonl")
        self.bridge = ProposalLedgerBridge(self.ledger)
        self.decisions = MutationDecisionLog(root / "mutation-decisions.jsonl")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ai_dual_write_links_commit_to_decision(self) -> None:
        legacy = AIProposalStore(self.ai_file)
        proxy = DualWriteAIProposalStore(legacy, self.bridge, self.decisions)
        proposal = proxy.create(
            action="toggle_fire", confidence=0.95, reason="test", original_text="fogueira",
            model="test", gateway_text="fogueira", actionable=True,
            source="api", actor_id="operator", display_name="Operator", metadata={},
        )
        mirrored = self.ledger.current()[0]
        self.assertEqual(mirrored["source_proposal_id"], proposal["proposal_id"])
        self.assertEqual(mirrored["status"], "proposed")

        decision = self.decisions.append(
            decision={"accepted": True, "reason": "accepted", "principal": {"authority": "operator"}, "operations": []},
            before_state_hash="a", after_state_hash="b", world_event_id="evt_9", context={},
        )
        proxy.mark_committed(proposal["proposal_id"], world_event_id="evt_9")
        current = self.ledger.current()[0]
        self.assertEqual(current["status"], "committed")
        self.assertEqual(current["mutation_decision_id"], decision["mutation_decision_id"])
        self.assertEqual(current["world_event_id"], "evt_9")

    def test_audience_append_mirror_is_idempotent(self) -> None:
        rows: list[dict] = []
        def append_fn(path: Path, record: dict) -> None:
            rows.append(dict(record))

        mirror = AudienceProposalAppendMirror(
            append_fn=append_fn,
            audience_file=self.audience_file,
            bridge=self.bridge,
            decisions=self.decisions,
        )
        proposal = {"proposal_id": "aud-1", "status": "pending", "gateway_text": "fogueira", "rule_id": "likes-50"}
        mirror(self.audience_file, proposal)
        mirror(self.audience_file, proposal)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(self.ledger.current()), 1)
        self.assertEqual(self.ledger.current()[0]["origin"], "audience")

    def test_audience_commit_resolves_mutation_decision_from_context(self) -> None:
        def append_fn(path: Path, record: dict) -> None:
            pass
        mirror = AudienceProposalAppendMirror(
            append_fn=append_fn,
            audience_file=self.audience_file,
            bridge=self.bridge,
            decisions=self.decisions,
        )
        mirror(self.audience_file, {"proposal_id": "aud-2", "status": "pending", "gateway_text": "fogueira", "rule_id": "likes-50"})
        decision = self.decisions.append(
            decision={"accepted": True, "reason": "accepted", "principal": {"authority": "operator"}, "operations": []},
            before_state_hash="a", after_state_hash="b", world_event_id="evt_10",
            context={"metadata": {"proposal_id": "aud-2"}},
        )
        mirror(self.audience_file, {"proposal_id": "aud-2", "status": "committed"})
        current = self.ledger.current()[0]
        self.assertEqual(current["status"], "committed")
        self.assertEqual(current["mutation_decision_id"], decision["mutation_decision_id"])
        self.assertEqual(current["world_event_id"], "evt_10")


if __name__ == "__main__":
    unittest.main()
