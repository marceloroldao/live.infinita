from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from importlib.util import find_spec

from packages.observability.local_memoria import (
    DB_NAME, LOCAL_SCHEMA, LOCAL_PROVENANCE, LocalMemoriaError,
    load_real_evidence_core, status, sync_once,
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


def read_checkpoint(local: Path) -> dict | None:
    with sqlite3.connect(local / DB_NAME) as db:
        row = db.execute("SELECT payload FROM checkpoint WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


@unittest.skipUnless(HAVE_REAL_MEMORIA, "Memoria.ia v2 RC2 checkout required")
class LocalMemoriaRealIntegrationTests(unittest.TestCase):
    def test_real_rc2_local_incremental_persistence_and_relation_path(self):
        from memoria_resolutiva.evidence_core import EvidenceCore
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(i) for i in range(3)])
            original = ledger.read_bytes()
            first = sync_once(ledger, world, local, limit=2)
            self.assertEqual(first["observations_in_batch"], 2)
            self.assertEqual(first["new_observations"], 2)
            self.assertEqual(first["new_relations"], 8)
            self.assertTrue(first["local_sqlite_transaction_committed"])
            self.assertFalse(first["central_transport_enabled"])
            self.assertFalse(first["world_mutated"])
            first_cp = status(local)
            self.assertEqual(first_cp["total_observations"], 2)
            self.assertEqual(first_cp["memoria_backend"], "sqlite-incremental")
            second = sync_once(ledger, world, local, limit=2)
            self.assertEqual(second["new_observations"], 1)
            self.assertEqual(second["total_relations"], 12)
            end = sync_once(ledger, world, local, limit=2)
            self.assertEqual(end["new_observations"], 0)
            self.assertEqual(end["source_cursor"], end["durable_local_cursor"])
            self.assertEqual(ledger.read_bytes(), original)
            self.assertEqual(status(local)["durable_local_cursor"], len(original))
            with sqlite3.connect(local / DB_NAME) as db:
                core, relation_count = load_real_evidence_core(db)
            self.assertIsInstance(core, EvidenceCore)
            edges = core.evidence_history(namespace="live:nov-live-autonomous-001")
            self.assertEqual(len(edges), relation_count)
            self.assertEqual(len(edges), 12)
            self.assertTrue(all(edge.provenance == LOCAL_PROVENANCE for edge in edges))
            event = next(edge.subject for edge in edges if edge.predicate == "observed_experience")
            result = core.infer_path(event, "live:entity:nov-live-autonomous-001:ancient_tree",
                                     namespace="live:nov-live-autonomous-001")
            self.assertTrue(result.inferred)
            self.assertEqual(result.paths[0].predicates, ("experienced_target",))
            self.assertNotIn('"role":', edges[0].source_text)

    def test_duplicate_replay_keeps_single_durable_record(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(0), observed(1)])
            sync_once(ledger, world, local, limit=2)
            cp = read_checkpoint(local)
            cp["cursor"] = 0
            cp["anchor_sha256"] = __import__("hashlib").sha256(b"").hexdigest()
            with sqlite3.connect(local / DB_NAME) as db:
                db.execute("UPDATE checkpoint SET payload=? WHERE id=1", (json.dumps(cp),))
            result = sync_once(ledger, world, local, limit=2)
            self.assertEqual(result["new_observations"], 0)
            self.assertEqual(result["duplicate_observations"], 2)
            self.assertEqual(result["total_observations"], 2)
            with sqlite3.connect(local / DB_NAME) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 2)

    def test_missing_checkpoint_conflict_and_source_rotation_block(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(0)])
            sync_once(ledger, world, local, limit=1)
            before = read_checkpoint(local)
            with ledger.open("ab") as fh:
                fh.write(json.dumps(observed(0, satisfaction=0.7)).encode() + b"\n")
            with self.assertRaisesRegex(LocalMemoriaError, "conflicting_local_observation"):
                sync_once(ledger, world, local)
            self.assertEqual(read_checkpoint(local), before)
            ledger.write_bytes(json.dumps(observed(0)).encode() + b"\n")
            with sqlite3.connect(local / DB_NAME) as db:
                db.execute("DELETE FROM checkpoint")
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
            self.assertEqual(first["new_observations"], 1)
            self.assertLess(first["durable_local_cursor"], ledger.stat().st_size)
            second = sync_once(ledger, world, local)
            self.assertEqual(second["new_observations"], 0)
            ledger.write_bytes(b"")
            with self.assertRaisesRegex(LocalMemoriaError, "cursor_beyond_ledger|ledger_truncated"):
                sync_once(ledger, world, local)

    def test_failure_does_not_commit_mixed_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            false = observed(1)
            false["role"] = "assistant"
            ledger, world, local = fixture(Path(directory), [observed(0), false])
            with self.assertRaisesRegex(LocalMemoriaError, "mixed_conversation_provenance"):
                sync_once(ledger, world, local)
            self.assertFalse(status(local)["initialized"])
            with sqlite3.connect(local / DB_NAME) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)

    def test_compact_growth_on_sixteen_real_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger, world, local = fixture(Path(directory), [observed(i) for i in range(16)])
            for _ in range(2):
                sync_once(ledger, world, local, limit=8)
            total = sum(p.stat().st_size for p in local.glob("memoria-local.sqlite3*"))
            self.assertLess(total, 2_000_000, total)
            self.assertEqual(status(local)["total_observations"], 16)
            with sqlite3.connect(local / DB_NAME) as db:
                core, relation_count = load_real_evidence_core(db)
            self.assertEqual(relation_count, 64)
            self.assertEqual(len(core.evidence_history(namespace="live:nov-live-autonomous-001")), 64)


class LocalMemoriaStaticContractTests(unittest.TestCase):
    def test_offline_oneshot_is_pinned_and_separate_from_single_writer(self):
        worker = (ROOT / "apps/world-runtime/local_memoria_worker.py").read_text()
        source = (ROOT / "packages/observability/local_memoria.py").read_text()
        self.assertIn("e38f27b639bec1cfcb83694c1418a4d01f250ffd", source)
        self.assertIn("from memoria_resolutiva.evidence_core import EvidenceCore", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS observations", source)
        self.assertIn('db.execute("BEGIN IMMEDIATE")', source)
        self.assertIn("PrivateNetwork=true", (ROOT / "deploy/live-infinita-local-memoria.service").read_text())
        self.assertNotIn("urlopen(", source + worker)
        self.assertNotIn("requests.post", source + worker)
        self.assertNotIn('sudo systemctl restart "$WORLD"', (ROOT / "deploy/mvp018c-local-memoria.sh").read_text())


if __name__ == "__main__":
    unittest.main()
