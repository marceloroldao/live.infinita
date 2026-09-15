from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.ai.proposals import AIProposalStore
from apps.ai.router import AIRouter
from apps.context.compiler import ContextCompiler


class ContextCompilerTests(unittest.TestCase):
    def test_bounded_slice_is_deterministic_without_rehydrating_world(self) -> None:
        compiler = ContextCompiler(max_entities=2, max_regions=2)
        world = {
            "world_id": "nov-live",
            "title": "Live Infinita",
            "version": 7,
            "sequence": 11,
            "state_hash": "abc123",
            "environment": {"period": "night"},
            "regions": [
                {"id": "clearing", "biome": "forest", "metadata": {"label": "Clareira"}},
                {"id": "shelter", "biome": "village", "metadata": {"label": "Abrigo"}},
                {"id": "far", "biome": "river", "metadata": {"label": "Rio"}},
            ],
            "entities": [],
        }
        rows = [
            {"id": "nov", "type": "human", "region_id": "clearing", "position": {"x": 1, "y": 2}},
            {"id": "fire_01", "type": "campfire", "region_id": "clearing", "position": {"x": 3, "y": 4}},
            {"id": "tree_01", "type": "tree", "region_id": "clearing", "position": {"x": 5, "y": 6}},
        ]
        package = compiler.compile(
            world=world,
            actor={"actor_key": "tiktok:42", "source": "tiktok", "actor_id": "42"},
            bound_entity_id="nov",
            entities=rows,
            entities_total=1000000,
            scope={"mode": "cold-region-plus-anchors", "region_ids": ["clearing"]},
        )
        repeated = compiler.compile(
            world=world,
            actor={"actor_key": "tiktok:42", "source": "tiktok", "actor_id": "42"},
            bound_entity_id="nov",
            entities=rows,
            entities_total=1000000,
            scope={"mode": "cold-region-plus-anchors", "region_ids": ["clearing"]},
        )

        self.assertEqual(package.digest, repeated.digest)
        self.assertEqual(package.world_version, 7)
        self.assertEqual(package.world_sequence, 11)
        self.assertEqual(package.payload["world"]["entities_total"], 1000000)
        self.assertEqual(len(package.payload["world"]["entities"]), 2)
        self.assertTrue(package.payload["world"]["entities_truncated"])
        self.assertEqual(package.payload["binding"]["status"], "active")
        self.assertFalse(package.payload["policy"]["direct_world_write"])


class AIRouterContextTests(unittest.TestCase):
    def test_router_receives_read_only_context_and_preserves_nov_actions(self) -> None:
        captured: dict = {}

        def transport(payload: dict) -> dict:
            captured.update(payload)
            return {"output_text": json.dumps({
                "action": "nov_to_shelter",
                "confidence": 0.93,
                "reason": "pedido explícito",
            })}

        router = AIRouter(api_key="test", model="test-model", transport=transport)
        proposal = router.propose(
            "Nov vai para o abrigo",
            context={"authority": "read-only-context", "context_digest": "digest-1"},
        )

        self.assertEqual(proposal.action, "nov_to_shelter")
        messages = captured["input"]
        context_messages = [
            part["text"]
            for message in messages
            for part in message.get("content", [])
            if "Context Package (read-only)" in str(part.get("text", ""))
        ]
        self.assertEqual(len(context_messages), 1)
        self.assertIn("read-only-context", context_messages[0])


class AIProposalContextTests(unittest.TestCase):
    def test_proposal_records_revision_and_can_be_marked_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AIProposalStore(Path(directory) / "proposals.jsonl")
            proposal = store.create(
                action="nov_to_fire",
                confidence=0.95,
                reason="teste",
                original_text="Nov na fogueira",
                model="test",
                gateway_text="nov fogueira",
                actionable=True,
                source="tiktok",
                actor_id="42",
                display_name="Pessoa",
                context_digest="digest-1",
                context_schema_version="1.1",
                context_world_version=4,
                context_world_sequence=9,
                context_world_state_hash="hash-old",
                context_scope={"mode": "cold-region-plus-anchors"},
            )
            self.assertEqual(proposal["context"]["world_sequence"], 9)
            stale = store.mark_stale(
                proposal["proposal_id"],
                current_world_version=5,
                current_world_sequence=10,
                current_world_state_hash="hash-new",
            )
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(stale["stale_world"]["state_hash"], "hash-new")


class DeploymentContractTests(unittest.TestCase):
    def test_systemd_uses_story_wrapper_over_cognitive_and_context_layers(self) -> None:
        unit = Path("deploy/live-infinita.service").read_text(encoding="utf-8")
        story = Path("apps/world-runtime/main_story_live.py").read_text(encoding="utf-8")
        cognitive = Path("apps/world-runtime/main_cognitive_live.py").read_text(encoding="utf-8")
        self.assertIn("main_story_live:app", unit)
        self.assertIn("LIVE_INFINITA_MEMORIA_V2_COGNITIVE_GYM=0", unit)
        self.assertIn("import main_cognitive_live", story)
        self.assertIn("app = main_cognitive_live.app", story)
        self.assertIn("import main_context_live", cognitive)
        self.assertIn("app = main_context_live.app", cognitive)

    def test_context_layer_replaces_only_ai_and_health_routes(self) -> None:
        source = Path("apps/world-runtime/main_context_live.py").read_text(encoding="utf-8")
        self.assertIn('_replace_route("/api/ai/proposals", "POST", create_ai_proposal)', source)
        self.assertIn('_replace_route("/api/ai/proposals/{proposal_id}/commit", "POST", commit_ai_proposal)', source)
        self.assertIn('_replace_route("/api/health", "GET", context_health)', source)
        self.assertIn("_context_expected_world", source)
        self.assertIn("actor_state_from_agent_output", source)

    def test_late_extension_routes_use_tested_precedence_helper(self) -> None:
        source = Path("apps/world-runtime/main_cognitive_live.py").read_text(encoding="utf-8")
        helper = Path("apps/world-runtime/route_precedence.py").read_text(encoding="utf-8")
        self.assertIn('promote_api_route_before_root(app, "/api/ai/context/preview")', source)
        self.assertIn('promote_api_route_before_root(app, "/api/cognitive/v2/frame")', source)
        self.assertIn("isinstance(route, Mount)", helper)
        self.assertIn('route.path in {"", "/"}', helper)


if __name__ == "__main__":
    unittest.main()