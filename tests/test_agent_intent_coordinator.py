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

from agent_intent_coordinator import AgentIntentCoordinator
from proposal_ledger import ProposalLedger


class FakeIntentService:
    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted

    def resolve(self, intent):
        return {"intent_type": intent["intent"], "operations": [{"op": "move"}], "rationale": "preview"}

    def commit_resolved(self, intent, *, principal, context=None, narration=""):
        if not self.accepted:
            return {
                "ok": False,
                "decision": {"accepted": False, "reason": "not authorized"},
                "audit": {"mutation_decision_id": "md_rejected"},
                "event": None,
            }
        return {
            "ok": True,
            "decision": {"accepted": True, "reason": "accepted"},
            "audit": {"mutation_decision_id": "md_001"},
            "event": {"event_id": "evt_001"},
            "delta": {"delta_id": "delta_001"},
            "world": {"state_hash": "hash_1"},
        }


class AgentIntentCoordinatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = ProposalLedger(Path(self.tmp.name) / "proposal-ledger.jsonl")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_submit_is_proposal_only(self) -> None:
        coordinator = AgentIntentCoordinator(self.ledger, FakeIntentService())
        proposal = coordinator.propose(
            {"intent": "move_to_entity", "actor_entity_id": "nov", "target_entity_id": "bridge"},
            origin="agent",
            proposer_id="nov-agent",
            idempotency_key="intent-1",
        )
        self.assertEqual(proposal["status"], "proposed")
        self.assertEqual(proposal["proposal_kind"], "agent_intent")
        self.assertIsNone(proposal.get("world_event_id"))

        duplicate = coordinator.propose(
            {"intent": "move_to_entity", "actor_entity_id": "nov", "target_entity_id": "bridge"},
            origin="agent",
            proposer_id="nov-agent",
            idempotency_key="intent-1",
        )
        self.assertEqual(duplicate["proposal_id"], proposal["proposal_id"])

    def test_approved_intent_links_decision_and_world_event(self) -> None:
        coordinator = AgentIntentCoordinator(self.ledger, FakeIntentService(accepted=True))
        proposal = coordinator.propose(
            {"intent": "move_to_entity", "actor_entity_id": "nov", "target_entity_id": "bridge"},
            origin="agent",
            proposer_id="nov-agent",
        )
        result = coordinator.approve_and_commit(
            proposal["proposal_id"],
            approved_by="operator",
            principal={"source": "agent", "actor_id": "nov-agent", "authority": "entity_agent", "subject_entity_id": "nov"},
        )
        self.assertTrue(result["ok"])
        final = self.ledger.get(proposal["proposal_id"])
        self.assertEqual(final["status"], "committed")
        self.assertEqual(final["mutation_decision_id"], "md_001")
        self.assertEqual(final["world_event_id"], "evt_001")

    def test_gate_rejection_becomes_terminal_rejected_proposal(self) -> None:
        coordinator = AgentIntentCoordinator(self.ledger, FakeIntentService(accepted=False))
        proposal = coordinator.propose(
            {"intent": "transfer_possession", "actor_entity_id": "npc", "object_entity_id": "gift", "recipient_entity_id": "nov"},
            origin="agent",
            proposer_id="npc-agent",
        )
        result = coordinator.approve_and_commit(
            proposal["proposal_id"],
            approved_by="operator",
            principal={"source": "agent", "actor_id": "npc-agent", "authority": "entity_agent", "subject_entity_id": "npc"},
        )
        self.assertFalse(result["ok"])
        final = self.ledger.get(proposal["proposal_id"])
        self.assertEqual(final["status"], "rejected")
        self.assertIn("not authorized", final["decision_reason"])


if __name__ == "__main__":
    unittest.main()
