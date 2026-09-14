from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from packages.spatial import AgentIntentError, AgentIntentResolver, FileRegionColdStore, MutationGate, MutationPrincipal


class AgentIntentProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileRegionColdStore(Path(self.tmp.name) / "cold")
        for entity in [
            {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}, "properties": {}},
            {"id": "bridge", "type": "bridge", "region_id": "r1", "position": {"x": 400, "y": 10}, "properties": {}},
            {"id": "npc", "type": "human", "region_id": "r0", "position": {"x": 20, "y": 0}, "properties": {}},
            {"id": "gift", "type": "item", "region_id": "r0", "position": {"x": 21, "y": 0}, "properties": {"owner_entity_id": "npc"}},
        ]:
            self.store.upsert(entity)
        self.resolver = AgentIntentResolver(self.store)
        self.gate = MutationGate()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_move_to_entity_resolves_target_position_and_region(self) -> None:
        resolved = self.resolver.resolve({
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
        })
        self.assertEqual(resolved.operations[0], {
            "op": "move",
            "entity_id": "nov",
            "position": {"x": 400.0, "y": 10.0},
            "region_id": "r1",
        })

    def test_entity_agent_can_move_only_itself(self) -> None:
        resolved = self.resolver.resolve({
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
        })
        decision = self.gate.decide(resolved.operations, MutationPrincipal(
            source="agent",
            actor_id="agent-nov",
            authority="entity_agent",
            subject_entity_id="nov",
        ))
        self.assertTrue(decision.accepted)

        other = self.resolver.resolve({
            "intent": "move_to_entity",
            "actor_entity_id": "npc",
            "target_entity_id": "bridge",
        })
        rejected = self.gate.decide(other.operations, MutationPrincipal(
            source="agent",
            actor_id="agent-nov",
            authority="entity_agent",
            subject_entity_id="nov",
        ))
        self.assertFalse(rejected.accepted)

    def test_environment_intent_requires_world_authority(self) -> None:
        resolved = self.resolver.resolve({
            "intent": "set_environment",
            "key": "weather",
            "value": "rain",
        })
        world_agent = self.gate.decide(resolved.operations, MutationPrincipal(
            source="agent", actor_id="director", authority="world_agent"
        ))
        operator = self.gate.decide(resolved.operations, MutationPrincipal(
            source="operator", actor_id="operator", authority="operator"
        ))
        self.assertFalse(world_agent.accepted)
        self.assertTrue(operator.accepted)

    def test_transfer_possession_resolves_but_entity_agent_cannot_self_authorize(self) -> None:
        resolved = self.resolver.resolve({
            "intent": "transfer_possession",
            "actor_entity_id": "npc",
            "object_entity_id": "gift",
            "recipient_entity_id": "nov",
        })
        self.assertEqual([op["op"] for op in resolved.operations], ["set", "link"])
        rejected = self.gate.decide(resolved.operations, MutationPrincipal(
            source="agent",
            actor_id="npc-agent",
            authority="entity_agent",
            subject_entity_id="npc",
        ))
        self.assertFalse(rejected.accepted)
        world_agent = self.gate.decide(resolved.operations, MutationPrincipal(
            source="agent",
            actor_id="world-director",
            authority="world_agent",
        ))
        self.assertTrue(world_agent.accepted)

    def test_relation_intents_resolve_without_mutating_store(self) -> None:
        before = self.store.get_entity("nov")
        resolved = self.resolver.resolve({
            "intent": "establish_relation",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
            "relation": "sees",
        })
        self.assertEqual(resolved.operations[0]["op"], "link")
        self.assertEqual(self.store.get_entity("nov"), before)

    def test_unknown_intent_and_missing_entities_fail_closed(self) -> None:
        with self.assertRaises(AgentIntentError):
            self.resolver.resolve({"intent": "teleport_everything"})
        with self.assertRaises(AgentIntentError):
            self.resolver.resolve({
                "intent": "move_to_entity",
                "actor_entity_id": "nov",
                "target_entity_id": "missing",
            })


if __name__ == "__main__":
    unittest.main()
