from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from packages.spatial import FileRegionColdStore, MutationGate, MutationPrincipal


class MutationGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bootstrap = root / "bootstrap.json"
        self.data_dir = root / "data"
        self.store = FileRegionColdStore(root / "cold")
        self.bootstrap.write_text(json.dumps({
            "world_id": "gate-test",
            "version": 1,
            "regions": [
                {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 200, "neighbors": []},
            ],
            "environment": {"period": "day"},
            "entities": [
                {"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}},
                {"id": "tree", "type": "tree", "region_id": "r0", "position": {"x": 20, "y": 0}},
            ],
            "narration": {"text": ""},
        }), encoding="utf-8")
        self.engine = ColdAuthoritativeWorldEngine(self.bootstrap, self.data_dir, self.store)
        self.service = GuardedMutationService(self.engine)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_audience_has_no_direct_mutation_rights(self) -> None:
        before_hash = self.engine.load_world()["state_hash"]
        result = self.service.commit(
            [{"op": "move", "entity_id": "nov", "position": {"x": 10, "y": 0}}],
            principal={"source": "tiktok", "actor_id": "viewer-1", "authority": "audience"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(self.store.get_entity("nov")["position"]["x"], 0)
        self.assertEqual(self.engine.load_world()["state_hash"], before_hash)
        self.assertEqual(self.engine.read_jsonl(self.engine.events_file), [])
        self.assertEqual(self.engine.read_jsonl(self.engine.deltas_file), [])

    def test_entity_agent_is_scoped_to_its_subject(self) -> None:
        principal = MutationPrincipal(
            source="agent",
            actor_id="nov-agent",
            authority="entity_agent",
            subject_entity_id="nov",
        )
        denied = self.service.commit(
            [{"op": "set", "entity_id": "tree", "path": ["properties", "marked"], "value": True}],
            principal=principal,
        )
        self.assertFalse(denied["ok"])
        self.assertIsNone(self.store.get_entity("tree").get("properties"))

        accepted = self.service.commit(
            [{"op": "move", "entity_id": "nov", "position": {"x": 50, "y": 5}}],
            principal=principal,
            context={"intent": "walk"},
        )
        self.assertTrue(accepted["ok"])
        self.assertEqual(self.store.get_entity("nov")["position"], {"x": 50.0, "y": 5.0})
        provenance = accepted["event"]["context"]["mutation_provenance"]
        self.assertEqual(provenance["authority"], "entity_agent")
        self.assertEqual(provenance["subject_entity_id"], "nov")
        self.assertEqual(provenance["policy"], "mutation_gate_v1")
        self.assertTrue(self.engine.verify_replay()["ok"])

    def test_world_agent_cannot_remove_or_set_world(self) -> None:
        principal = {"source": "planner", "actor_id": "world-ai", "authority": "world_agent"}
        remove = MutationGate().decide([{"op": "remove", "entity_id": "tree"}], principal)
        set_world = MutationGate().decide(
            [{"op": "set_world", "path": ["environment", "period"], "value": "night"}],
            principal,
        )
        self.assertFalse(remove.accepted)
        self.assertFalse(set_world.accepted)
        self.assertIn("cannot perform remove", remove.reason)
        self.assertIn("cannot perform set_world", set_world.reason)

    def test_operator_can_commit_world_and_entity_changes_with_provenance(self) -> None:
        result = self.service.commit(
            [
                {"op": "set", "entity_id": "tree", "path": ["properties", "marked"], "value": True},
                {"op": "set_world", "path": ["environment", "period"], "value": "night"},
            ],
            principal={"source": "operator-api", "actor_id": "operator", "authority": "operator"},
            narration="O operador altera o estado.",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(self.store.get_entity("tree")["properties"]["marked"])
        self.assertEqual(result["world"]["environment"]["period"], "night")
        self.assertEqual(result["event"]["source"], "operator-api")
        self.assertEqual(result["event"]["context"]["mutation_provenance"]["decision"], "accepted")
        self.assertTrue(self.engine.verify_replay()["ok"])


if __name__ == "__main__":
    unittest.main()
