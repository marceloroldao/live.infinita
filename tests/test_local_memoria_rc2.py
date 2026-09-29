from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from packages.observability.local_memoria import (
    LOCAL_SCHEMA, LOCAL_PROVENANCE, LocalMemoriaError, _anchor,
    status, sync_once,
)


ROOT = Path(__file__).resolve().parents[1]
HAVE_REAL_MEMORIA = find_spec("memoria_resolutiva") is not None


def observed(index: int, *, satisfaction: float = 0.3) -> dict:
    plan = f"local_{index}"
    return {
        "episode_schema": "npc_episode_v1",
        "episode_id": "plan:" + plan,
        "npc_id": "nov",
        "logical_tick": index + 100,
        "need": "curiosity",
        "target_entity_id": "ancient_tree",
        "strategy_id": "visit:ancient_tree",
        "context": {"period": "night", "weather": "clear", "region_id": "clearing", "danger_level": 0.1},
        "outcome": {"satisfaction": satisfaction, "observed_risk": 0.1, "elapsed_ticks": 4, "preemptions": 0, "replans": 0},
        "source": {"kind": "need_outcome", "plan_id": plan, "plan_revision": 0, "proposal_id": f"proposal_{index}"},
    }


def fixture(path: Path, rows: list[dict]) -> tuple[Path, Path, Path]:
    source = path / "world"
    source.mkdir(exist_ok=True)
    ledger = source / "npc-episodes.jsonl"
    world = source / "world.json"
    world.write_text(json.dumps({"world_id": "nov-live-autonomous-001", "version": 1}), encoding="utf-8")
    ledger.write_bytes(b"".join(json.dumps(row, ensure_ascii=False).encode() + b"\n" for row in rows))
    return ledger, world, path / "local"


@unittest.skipUnless(HAVE_REAL_MEMORIA, "Memoria.ia v2 RC2 checkout required")
class LocalMemoriaRealIntegrationTests(unittest.TestCase):
    def test_real_rc2_local_incremental_persistence_and_relation_path(self):
        from memoria_resolutiva.product_evidence import ProductEvidenceService
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(i) for i in range(3)])
            original = ledger.read_bytes()
            first = sync_once(ledger, world, local, limit=2)
            self.assertEqual(first["observations_in_batch"], 2)
            self.assertEqual(first["new_relations"], 8)
            self.assertTrue(first["local_snapshot_persisted"])
            self.assertFalse(first["central_transport_enabled"])
            self.assertFalse(first["world_mutated"])
            first_cp = status(local)
            self.assertEqual(first_cp["total_relations"], 8)
            self.assertEqual(first_cp["memoria_backend"], "sqlite")
            second = sync_once(ledger, world, local, limit=2)
            self.assertEqual(second["new_relations"], 4)
            self.assertEqual(second["total_relations"], 12)
            end = sync_once(ledger, world, local, limit=2)
            self.assertEqual(end["new_relations"], 0)
            self.assertEqual(end["source_cursor"], end["durable_local_cursor"])
            self.assertEqual(ledger.read_bytes(), original)
            self.assertEqual(status(local)["durable_local_cursor"], len(original))
            service = ProductEvidenceService.open(local / "evidence", backend="sqlite", allow_fallback=False)
            edges = service.core.evidence_history(namespace="live:nov-live-autonomous-001")
            self.assertEqual(len(edges), 12)
            self.assertTrue(all(edge.provenance == LOCAL_PROVENANCE for edge in edges))
            event = next(edge.subject for edge in edges if edge.predicate == "observed_experience")
            result = service.core.infer_path(event, "live:entity:nov-live-autonomous-001:ancient_tree",
                                             namespace="live:nov-live-autonomous-001")
            self.assertTrue(result.inferred)
            self.assertEqual(result.paths[0].predicates, ("experienced_target",))
            self.assertEqual(service.receipt.backend, "sqlite")
            self.assertNotIn('"role":', edges[0].source_text)

    def test_duplicate_after_save_before_checkpoint_is_idempotent(self):
        from memoria_resolutiva.product_evidence import ProductEvidenceService
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(0), observed(1)])
            first = sync_once(ledger, world, local, limit=2)
            cp_path = local / "checkpoint.json"
            cp = json.loads(cp_path.read_text())
            cp["cursor"] = 0
            cp["anchor_sha256"] = sha256(b"").hexdigest()
            cp["edge_count"] = 0
            cp_path.write_text(json.dumps(cp))
            result = sync_once(ledger, world, local, limit=2)
            self.assertEqual(result["new_relations"], 0)
            self.assertEqual(result["duplicate_relations"], 8)
            self.assertEqual(result["total_relations"], 8)
            reopened = ProductEvidenceService.open(local / "evidence", backend="sqlite", allow_fallback=False)
            self.assertEqual(len(reopened.core.evidence_history(namespace="live:nov-live-autonomous-001")), 8)

    def test_missing_checkpoint_conflicting_duplicate_and_source_rotation_block(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(0)])
            sync_once(ledger, world, local, limit=1)
            checkpoint = (local / "checkpoint.json").read_bytes()
            with ledger.open("ab") as fh:
                fh.write(json.dumps(observed(0, satisfaction=0.7)).encode() + b"\n")
            with self.assertRaisesRegex(LocalMemoriaError, "conflicting_local_observation"):
                sync_once(ledger, world, local)
            self.assertEqual((local / "checkpoint.json").read_bytes(), checkpoint)
            (local / "checkpoint.json").unlink()
            with self.assertRaisesRegex(LocalMemoriaError, "checkpoint_missing_for_existing_memory"):
                sync_once(ledger, world, local)
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(0)])
            sync_once(ledger, world, local)
            ledger.rename(ledger.with_suffix(".old"))
            ledger.write_bytes(json.dumps(observed(0)).encode() + b"\n")
            with self.assertRaisesRegex(LocalMemoriaError, "local_source_identity_changed"):
                sync_once(ledger, world, local)

    def test_truncation_and_incomplete_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(0)])
            with ledger.open("ab") as fh:
                fh.write(b'{"episode_id":"incomplete"')
            first = sync_once(ledger, world, local, limit=3)
            self.assertEqual(first["new_relations"], 4)
            self.assertLess(first["durable_local_cursor"], ledger.stat().st_size)
            second = sync_once(ledger, world, local)
            self.assertEqual(second["new_relations"], 0)
            with ledger.open("wb") as fh:
                fh.write(b"")
            with self.assertRaisesRegex(LocalMemoriaError, "cursor_beyond_ledger|ledger_truncated"):
                sync_once(ledger, world, local)

    def test_failure_does_not_checkpoint_mixed_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            false = observed(1)
            false["role"] = "assistant"
            ledger, world, local = fixture(Path(directory), [observed(0), false])
            with self.assertRaisesRegex(LocalMemoriaError, "mixed_conversation_provenance"):
                sync_once(ledger, world, local)
            self.assertFalse((local / "checkpoint.json").exists())
            self.assertFalse((local / "evidence" / "receipt.json").exists())


class LocalMemoriaStaticContractTests(unittest.TestCase):
    def test_offline_oneshot_is_pinned_and_separate_from_single_writer(self):
        worker = (ROOT / "apps/world-runtime/local_memoria_worker.py").read_text()
        source = (ROOT / "packages/observability/local_memoria.py").read_text()
        self.assertIn("e38f27b639bec1cfcb83694c1418a4d01f250ffd", source)
        self.assertIn("from memoria_resolutiva.product_evidence import ProductEvidenceService", source)
        self.assertIn('backend="sqlite", allow_fallback=False', source)
        self.assertIn('service.save().as_dict()', source)
        self.assertIn("PrivateNetwork=true", (ROOT / "deploy/live-infinita-local-memoria.service").read_text())
        self.assertNotIn("urlopen(", source + worker)
        self.assertNotIn("requests.post", source + worker)
        self.assertNotIn("sudo systemctl restart \"$WORLD\"", (ROOT / "deploy/mvp018c-local-memoria.sh").read_text())


if __name__ == "__main__":
    unittest.main()
