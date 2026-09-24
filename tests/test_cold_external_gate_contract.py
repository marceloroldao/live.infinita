from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from packages.spatial import FileRegionColdStore, MutationPrincipal


class ColdExternalGateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bootstrap = root / "bootstrap.json"
        self.bootstrap.write_text(json.dumps({
            "world_id": "gate-e2e",
            "version": 1,
            "regions": [{"id": "r0", "center": {"x": 0, "y": 0}, "radius": 300, "neighbors": []}],
            "environment": {"period": "day"},
            "entities": [
                {"id": "tree_01", "type": "tree", "region_id": "r0", "position": {"x": 20, "y": 0}, "properties": {}},
                {"id": "fire_01", "type": "campfire", "region_id": "r0", "position": {"x": 80, "y": 0}, "properties": {"lit": True}},
            ],
            "narration": {"text": ""},
        }), encoding="utf-8")
        self.store = FileRegionColdStore(root / "cold")
        self.engine = ColdAuthoritativeWorldEngine(self.bootstrap, root / "data", self.store)
        self.service = GuardedMutationService(self.engine)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_audience_direct_mutation_is_rejected_without_state_change(self) -> None:
        before = self.engine.load_world()
        result = self.service.commit(
            [{"op": "set", "entity_id": "fire_01", "path": ["properties", "lit"], "value": False}],
            principal=MutationPrincipal(source="tiktok", actor_id="viewer-1", authority="audience"),
        )
        after = self.engine.load_world()
        self.assertFalse(result["ok"])
        self.assertEqual(before["state_hash"], after["state_hash"])
        self.assertTrue(self.store.get_entity("fire_01")["properties"]["lit"])
        self.assertEqual(self.engine.read_jsonl(self.engine.events_file), [])
        self.assertEqual(self.engine.read_jsonl(self.engine.deltas_file), [])

    def test_operator_approved_ai_mutation_is_committed_with_provenance(self) -> None:
        result = self.service.commit(
            [{"op": "set", "entity_id": "fire_01", "path": ["properties", "lit"], "value": False}],
            principal=MutationPrincipal(source="agent", actor_id="ai-router", authority="operator"),
            context={"ai_proposal_id": "ai_001"},
        )
        self.assertTrue(result["ok"])
        self.assertFalse(self.store.get_entity("fire_01")["properties"]["lit"])
        provenance = result["event"]["context"]["mutation_provenance"]
        self.assertEqual(provenance["authority"], "operator")
        self.assertEqual(provenance["policy"], "mutation_gate_v1")
        self.assertTrue(self.engine.verify_replay()["ok"])

    def test_system_can_mutate_world(self) -> None:
        result = self.service.commit(
            [{"op": "set_world", "path": ["environment", "period"], "value": "night"}],
            principal=MutationPrincipal(source="api", actor_id="system", authority="system"),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(self.engine.load_world()["environment"]["period"], "night")
        self.assertTrue(self.engine.verify_replay()["ok"])

    def test_runtime_wrapper_contract_is_present(self) -> None:
        source = (RUNTIME / "main_spatial.py").read_text(encoding="utf-8")
        self.assertIn("_install_cold_mutation_gate", source)
        self.assertIn("metadata.get(\"ai_proposal_id\")", source)
        self.assertIn("authority = \"audience\"", source)
        self.assertIn("GuardedMutationService", source)
        self.assertIn("mutation rejected by policy", source)


if __name__ == "__main__":
    unittest.main()
