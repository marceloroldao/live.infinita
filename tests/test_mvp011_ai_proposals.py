import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / "apps" / "ai"
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from proposals import AIProposalStore  # noqa: E402


class AIProposalStoreTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AIProposalStore(Path(self.tempdir.name) / "ai-proposals.jsonl")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_pending_proposal_is_side_channel_only(self):
        proposal = self.store.create(
            action="set_night",
            confidence=0.94,
            reason="pedido para anoitecer",
            original_text="deixa o mundo mais escuro",
            model="fake-model",
            gateway_text="noite",
            actionable=True,
            source="api",
            actor_id="tester",
            display_name="Tester",
            metadata={"test": True},
        )
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(len(self.store.history()), 1)
        self.assertEqual(len(self.store.current()), 1)

    def test_commit_is_append_only_but_current_is_folded(self):
        proposal = self.store.create(
            action="toggle_fire",
            confidence=1.0,
            reason="pedido explícito",
            original_text="mexa na fogueira",
            model="fake-model",
            gateway_text="fogueira",
            actionable=True,
            source="api",
            actor_id="tester",
            display_name=None,
        )
        committed = self.store.mark_committed(proposal["proposal_id"], world_event_id="evt_123")
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(len(self.store.history()), 2)
        self.assertEqual(len(self.store.current()), 1)
        self.assertEqual(self.store.current()[0]["status"], "committed")
        self.assertEqual(self.store.current()[0]["world_event_id"], "evt_123")

    def test_non_actionable_proposal_cannot_be_committed(self):
        proposal = self.store.create(
            action=None,
            confidence=0.2,
            reason="intenção incerta",
            original_text="talvez alguma coisa",
            model="fake-model",
            gateway_text=None,
            actionable=False,
            source="api",
            actor_id="tester",
            display_name=None,
        )
        self.assertEqual(proposal["status"], "non_actionable")
        with self.assertRaises(ValueError):
            self.store.mark_committed(proposal["proposal_id"])

    def test_reject_pending_proposal(self):
        proposal = self.store.create(
            action="move_tree",
            confidence=0.9,
            reason="pedido de movimento",
            original_text="leve a árvore para o lado",
            model="fake-model",
            gateway_text="mover árvore",
            actionable=True,
            source="api",
            actor_id="tester",
            display_name=None,
        )
        rejected = self.store.mark_rejected(proposal["proposal_id"], reason="operador recusou")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(len(self.store.history()), 2)
        self.assertEqual(len(self.store.current()), 1)


if __name__ == "__main__":
    unittest.main()
