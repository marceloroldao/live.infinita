import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_DIR = ROOT / "apps" / "context"
AI_DIR = ROOT / "apps" / "ai"
for path in (CONTEXT_DIR, AI_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from compiler import ContextCompiler  # noqa: E402
from proposals import AIProposalStore  # noqa: E402
from router import AIRouter  # noqa: E402


WORLD = {
    "world_id": "w1",
    "title": "Teste",
    "version": 7,
    "sequence": 6,
    "state_hash": "abc123",
    "environment": {"period": "day"},
    "entities": [
        {
            "id": "person_01",
            "type": "human",
            "position": {"x": 1, "y": 2},
            "scale": 1.0,
            "properties": {"label": "Visitante"},
        },
        {
            "id": "tree_01",
            "type": "tree",
            "position": {"x": 3, "y": 4},
            "scale": 1.0,
            "properties": {"label": "Árvore"},
        },
    ],
}

ACTOR = {
    "actor_key": "tiktok:user-1",
    "source": "tiktok",
    "actor_id": "user-1",
    "display_name": "User One",
    "first_seen_unix": 1.0,
    "last_seen_unix": 2.0,
    "interactions_total": 3,
    "interactions_by_kind": {"join": 1, "text": 2},
    "last_interaction": {"kind": "text", "source_event_id": "evt-x", "observed_at_unix": 2.0},
}


class ContextCompilerTest(unittest.TestCase):
    def test_same_inputs_produce_same_digest(self):
        compiler = ContextCompiler()
        first = compiler.compile(world=WORLD, actor=ACTOR, bound_entity_id="person_01")
        second = compiler.compile(world=WORLD, actor=ACTOR, bound_entity_id="person_01")
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_world_change_changes_digest(self):
        compiler = ContextCompiler()
        first = compiler.compile(world=WORLD, actor=ACTOR, bound_entity_id="person_01")
        changed = {**WORLD, "version": 8, "sequence": 7, "state_hash": "def456"}
        second = compiler.compile(world=changed, actor=ACTOR, bound_entity_id="person_01")
        self.assertNotEqual(first.digest, second.digest)

    def test_binding_contains_relevant_entity(self):
        package = ContextCompiler().compile(world=WORLD, actor=ACTOR, bound_entity_id="person_01")
        self.assertEqual(package.payload["binding"]["status"], "active")
        self.assertEqual(package.payload["binding"]["entity"]["id"], "person_01")
        self.assertFalse(package.payload["policy"]["direct_world_write"])

    def test_entity_list_is_bounded_and_reports_truncation(self):
        package = ContextCompiler(max_entities=1).compile(world=WORLD)
        self.assertEqual(len(package.payload["world"]["entities"]), 1)
        self.assertEqual(package.payload["world"]["entities_total"], 2)
        self.assertTrue(package.payload["world"]["entities_truncated"])


class RouterContextTest(unittest.TestCase):
    def test_context_package_is_sent_as_read_only_input(self):
        captured = {}

        def transport(payload):
            captured.update(payload)
            return {"output_text": '{"action":"set_night","confidence":0.9,"reason":"pedido"}'}

        context = ContextCompiler().compile(world=WORLD, actor=ACTOR, bound_entity_id="person_01").to_dict()
        proposal = AIRouter(api_key="test", model="gpt-test", transport=transport).propose(
            "anoiteça",
            context=context,
        )
        self.assertEqual(proposal.action, "set_night")
        serialized_messages = str(captured["input"])
        self.assertIn("Context Package", serialized_messages)
        self.assertIn("context_digest", serialized_messages)
        self.assertIn("read-only", serialized_messages)


class ProposalStaleTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AIProposalStore(Path(self.tempdir.name) / "ai-proposals.jsonl")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_context_provenance_is_persisted_and_can_be_marked_stale(self):
        proposal = self.store.create(
            action="set_night",
            confidence=0.95,
            reason="pedido",
            original_text="anoiteça",
            model="fake",
            gateway_text="noite",
            actionable=True,
            source="tiktok",
            actor_id="user-1",
            display_name="User One",
            context_digest="digest-1",
            context_schema_version="1.0",
            context_world_version=7,
            context_world_sequence=6,
            context_world_state_hash="abc123",
            context_actor_key="tiktok:user-1",
            context_bound_entity_id="person_01",
        )
        self.assertEqual(proposal["context"]["digest"], "digest-1")
        stale = self.store.mark_stale(
            proposal["proposal_id"],
            current_world_version=8,
            current_world_sequence=7,
            current_world_state_hash="def456",
        )
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["stale_world"]["version"], 8)
        self.assertEqual(len(self.store.history()), 2)
        self.assertEqual(len(self.store.current()), 1)
        self.assertEqual(self.store.current()[0]["status"], "stale")


if __name__ == "__main__":
    unittest.main()
