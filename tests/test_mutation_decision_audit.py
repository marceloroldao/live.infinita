from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

SERVICE = RUNTIME / "mutation_gate_service.py"
spec = importlib.util.spec_from_file_location("mutation_gate_service_audit_test", SERVICE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["mutation_gate_service_audit_test"] = module
spec.loader.exec_module(module)
GuardedMutationService = module.GuardedMutationService


class FakeEngine:
    def __init__(self) -> None:
        self.world = {"state_hash": "hash-0", "sequence": 0}
        self.commits = 0

    def load_world(self):
        return deepcopy(self.world)

    def commit_operations(self, operations, *, source, context, narration):
        self.commits += 1
        self.world = {"state_hash": f"hash-{self.commits}", "sequence": self.commits}
        event = {"event_id": f"evt_{self.commits:06d}", "context": deepcopy(context)}
        delta = {"operations": deepcopy(operations), "sequence": self.commits}
        return event, delta, deepcopy(self.world)


class MutationDecisionAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_file = Path(self.tmp.name) / "mutation-decisions.jsonl"
        self.engine = FakeEngine()
        self.service = GuardedMutationService(self.engine, decision_log_file=self.log_file)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rejection_is_logged_without_world_mutation(self) -> None:
        before = self.engine.load_world()
        result = self.service.commit(
            [{"op": "move", "entity_id": "nov", "position": {"x": 2, "y": 3}}],
            principal={"source": "tiktok", "actor_id": "viewer-1", "authority": "audience"},
            context={"proposal_id": "p1"},
        )
        after = self.engine.load_world()

        self.assertFalse(result["ok"])
        self.assertEqual(self.engine.commits, 0)
        self.assertEqual(before, after)
        rows = self.service.decision_log.read_all()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["accepted"])
        self.assertFalse(rows[0]["state_changed"])
        self.assertEqual(rows[0]["before_state_hash"], "hash-0")
        self.assertEqual(rows[0]["after_state_hash"], "hash-0")
        self.assertIsNone(rows[0]["world_event_id"])

    def test_acceptance_links_audit_record_to_authoritative_event(self) -> None:
        result = self.service.commit(
            [{"op": "set_world", "path": ["environment", "period"], "value": "night"}],
            principal={"source": "api", "actor_id": "operator", "authority": "operator"},
            context={"approval_id": "approval-1"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(self.engine.commits, 1)
        rows = self.service.decision_log.read_all()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["accepted"])
        self.assertTrue(rows[0]["state_changed"])
        self.assertEqual(rows[0]["world_event_id"], "evt_000001")
        self.assertEqual(rows[0]["before_state_hash"], "hash-0")
        self.assertEqual(rows[0]["after_state_hash"], "hash-1")
        provenance = result["event"]["context"]["mutation_provenance"]
        self.assertEqual(provenance["policy"], "mutation_gate_v1")
        self.assertEqual(provenance["authority"], "operator")


if __name__ == "__main__":
    unittest.main()
