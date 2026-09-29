"""MVP-018E Nov recall: isolated selection and real pinned V2 snapshot smoke."""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "apps/world-runtime/nov_memory_recall_shadow.py"
spec = importlib.util.spec_from_file_location("nov_recall", MODULE)
nov = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(nov)


def record(key: str, *, tick: int, **addresses: str) -> dict:
    return {
        "record_key": key, "logical_tick": tick, "addresses": addresses,
        "observation": {}, "evidence_id": "proof-" + key,
    }


class AddressRetrievalTests(unittest.TestCase):
    def test_intersection_recency_and_seed_exclusion(self) -> None:
        data = [
            record("old", tick=3, need="hunger", region_id="forest"),
            record("new", tick=8, need="hunger", region_id="forest"),
            record("different", tick=10, need="thirst", region_id="forest"),
            record("seed", tick=11, need="hunger", region_id="forest"),
        ]
        related, matched = nov.select_related(
            data, query={"need": "hunger", "region_id": "forest"},
            exclude_key="seed", limit=3,
        )
        self.assertEqual(matched, 3)
        self.assertEqual([row["record_key"] for row in related], ["new", "old", "different"])
        self.assertEqual(len(related[0]["matching_addresses"]), 2)

    def test_empty_address_graph_returns_no_invented_answer(self) -> None:
        related, matched = nov.select_related(
            [record("a", tick=2, need="shelter")], query={"need": "water"},
            exclude_key=None, limit=5,
        )
        self.assertEqual((related, matched), ([], 0))

    def test_invalid_queries_and_limits_fail_closed(self) -> None:
        for query in ({}, {"made_up": "x"}, {"need": ""}):
            with self.assertRaises(nov.RecallBlocked):
                nov.select_related([], query=query, exclude_key=None, limit=5)
        for limit in (0, 9, True):
            with self.assertRaises(nov.RecallBlocked):
                nov.select_related([], query={"need": "hunger"}, exclude_key=None, limit=limit)

    def test_address_projection_never_reads_narration(self) -> None:
        observation = {
            "need": "hunger", "strategy_id": "find_food", "target_entity_id": "tree",
            "context": {"region_id": "forest", "weather": "rain", "period": "day"},
            "text": "LLM hallucination",
        }
        self.assertEqual(set(nov._address_view(observation)), set(nov.FIELDS))
        self.assertNotIn("text", nov._address_view(observation))

    def test_wrapper_stays_manual_and_private(self) -> None:
        wrapper = (MODULE.parents[2] / "deploy/mvp018e-nov-recall-shadow.sh").read_text()
        self.assertIn('sudo -u liveinfinita env PYTHONPATH="$CORE" "$PY" -', wrapper)
        self.assertIn('( cd / && sudo -u liveinfinita', wrapper)
        self.assertIn('< "$REPO/apps/world-runtime/nov_memory_recall_shadow.py"', wrapper)
        self.assertNotIn("MEMORIA_EXTERNAL_EPISODE_PERSISTENCE=bdr", wrapper)
        self.assertNotIn("systemctl restart", wrapper)
        self.assertNotIn("systemctl enable", wrapper)


class GenuineV2SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from memoria_resolutiva.external_episode_contract import ExternalEpisodeRequest, canonical
            from memoria_resolutiva.external_episode_incremental import IncrementalExternalEpisodeStore
        except ImportError as exc:
            raise unittest.SkipTest("exact Memoria V2 core not installed in this test environment") from exc
        cls.Request = ExternalEpisodeRequest
        cls.canonical = staticmethod(canonical)
        cls.Store = IncrementalExternalEpisodeStore

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.mem = root / "memoria-local"
        self.mem.mkdir(mode=0o700)
        self.source_dir = self.mem / "external-episodes-incremental"
        self.store = self.Store(self.source_dir)
        self.addCleanup(self.store.close)
        self.source = self.source_dir / nov.SOURCE_NAME
        self.world = root / "world.json"
        self.world.write_text(json.dumps({
            "world_id": "nov-test", "environment": {"period": "day", "weather": "sun"},
        }))
        self.checkpoint = self.mem / "nov-ingest.checkpoint.json"

    def append(self, plan: str, tick: int, need: str, *, region: str = "forest") -> dict:
        source = {
            "system": "live.infinita", "world_id": "nov-test", "entity_id": "nov",
            "episode_id": "plan:" + plan, "source_schema": "npc_episode_v1",
            "source_kind": "need_outcome", "plan_id": plan,
            "proposal_id": "proposal-" + plan, "plan_revision": 0,
        }
        identity = {key: source[key] for key in ("system", "world_id", "entity_id", "episode_id")}
        unsigned = {
            "schema": "live-infinita-npc-episode-observation/v1",
            "record_key": sha256(self.canonical(identity)).hexdigest(),
            "source": source,
            "observation": {
                "logical_tick": tick, "need": need, "target_entity_id": "ancient_tree",
                "strategy_id": "search", "context": {
                    "period": "day", "weather": "sun", "region_id": region,
                    "danger_level": None,
                },
                "outcome": {"satisfaction": 0.5, "observed_risk": 0.1,
                            "elapsed_ticks": 1, "preemptions": 0, "replans": 0},
            },
            "authority": "observed-outcome-only", "world_write_authority": False,
        }
        proto = self.Request.model_validate({**unsigned, "content_sha256": "0" * 64})
        canonical_unsigned = proto.model_dump(mode="json", exclude={"content_sha256"})
        envelope = self.Request.model_validate({
            **canonical_unsigned,
            "content_sha256": sha256(self.canonical(canonical_unsigned)).hexdigest(),
        })
        receipt = self.store.observe(envelope)
        self.assertTrue(receipt["ack"])
        return receipt

    def watermark(self, receipt: dict) -> None:
        self.checkpoint.write_text(json.dumps({
            "schema": nov.CHECKPOINT_SCHEMA, "cursor": 1, "world_id": "nov-test",
            "last_acked_record_key": receipt["record_key"],
            "last_acked_content_sha256": receipt["content_sha256"],
        }))

    def test_real_v2_rehydrates_and_recalls_without_cutover(self) -> None:
        first = self.append("p1", 3, "hunger")
        self.append("p2", 5, "thirst")
        last = self.append("p3", 9, "hunger")
        self.watermark(last)
        original_count = self.store.count
        out = nov.recall_once(
            source=self.source, world_path=self.world,
            checkpoint_path=self.checkpoint, private_root=self.mem,
        )
        self.assertEqual(out["source_snapshot_records"], original_count)
        self.assertEqual(out["nov_observations"], 3)
        self.assertEqual(out["query_basis"], "latest_confirmed_episode")
        self.assertTrue(out["checkpoint_watermark_in_snapshot"])
        self.assertTrue(out["checkpoint_unchanged_during_copy"])
        self.assertEqual(out["selected"][0]["logical_tick"], 3)
        self.assertFalse(out["world_mutated"])
        self.assertFalse(out["selection_authority"])
        self.assertFalse(out["bdr_used"])
        self.assertEqual(self.store.count, original_count)
        self.assertEqual(self.world.read_text()[:1], "{")
        self.assertEqual(self.checkpoint.stat().st_mode & 0o777, 0o644)
        self.assertFalse(list(self.mem.glob("nov-recall-*")))
        self.assertEqual(first["record_key"] in (last["record_key"],), False)

    def test_checkpoint_mismatch_fail_closed_without_source_change(self) -> None:
        last = self.append("p1", 3, "hunger")
        self.watermark(last)
        original_source = self.store._db.execute("SELECT COUNT(*) FROM observations").fetchone()
        broken = json.loads(self.checkpoint.read_text())
        broken["last_acked_content_sha256"] = "f" * 64
        self.checkpoint.write_text(json.dumps(broken))
        with self.assertRaises(nov.RecallBlocked):
            nov.recall_once(
                source=self.source, world_path=self.world,
                checkpoint_path=self.checkpoint, private_root=self.mem,
            )
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM observations").fetchone(), original_source)

    def test_cross_world_checkpoint_is_not_consulted(self) -> None:
        last = self.append("p1", 3, "hunger")
        self.watermark(last)
        self.world.write_text(json.dumps({"world_id": "other-world", "environment": {}}))
        with self.assertRaises(nov.RecallBlocked):
            nov.recall_once(
                source=self.source, world_path=self.world,
                checkpoint_path=self.checkpoint, private_root=self.mem,
            )

    def test_empty_journal_abstains(self) -> None:
        self.checkpoint.write_text(json.dumps({
            "schema": nov.CHECKPOINT_SCHEMA, "cursor": 0, "world_id": "nov-test",
        }))
        out = nov.recall_once(
            source=self.source, world_path=self.world,
            checkpoint_path=self.checkpoint, private_root=self.mem,
        )
        self.assertEqual(out["query_basis"], "memory_empty")
        self.assertEqual(out["selected"], [])
        self.assertEqual(out["historical_matches"], 0)


if __name__ == "__main__":
    unittest.main()
