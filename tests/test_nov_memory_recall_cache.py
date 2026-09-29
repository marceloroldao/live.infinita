"""Versioned, bounded Nov memory-cache contracts; synthetic source only."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from memoria_v2_adapter import build_nov_cognitive_frame  # noqa: E402
from nov_memory_recall_cache import VersionedNovRecallCache, RecallBlocked  # noqa: E402
from nov_memory_recall_shadow import SCHEMA, CHECKPOINT_SCHEMA  # noqa: E402
from nov_memory_context_shadow import freeze_memory_context  # noqa: E402


def row(key: str, tick: int, need: str, region: str, weather: str = "sun") -> dict:
    return {
        "record_key": key * 64, "evidence_id": "live-obs:" + key * 40,
        "content_sha256": "f" * 64, "logical_tick": tick,
        "addresses": {"need": need, "region_id": region, "weather": weather, "period": "day"},
        "observation": {
            "logical_tick": tick, "need": need, "target_entity_id": "ancient_tree",
            "strategy_id": "walk", "context": {
                "region_id": region, "period": "day", "weather": weather,
            }, "outcome": {"satisfaction": 0.4},
        },
    }


class CacheContracts(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.private = root / "memoria-local"
        self.private.mkdir(mode=0o700)
        folder = self.private / "external-episodes-incremental"
        folder.mkdir()
        self.source = folder / "external-episodes.sqlite3"
        self.source.write_bytes(b"synthetic-only")
        self.wal = Path(str(self.source) + "-wal")
        self.world = root / "world.json"
        self.world.write_text(json.dumps({"world_id": "nov-test", "environment": {}}))
        self.checkpoint = self.private / "nov-ingest.checkpoint.json"
        self.checkpoint.write_text(json.dumps({
            "schema": CHECKPOINT_SCHEMA, "world_id": "nov-test", "cursor": 0,
        }))
        self.rows = [
            row("a", 3, "curiosity", "clearing"),
            row("b", 8, "safety", "clearing"),
            row("c", 12, "curiosity", "clearing"),
        ]
        self.calls = 0
        self.now = [0.0]

        def load(**params):
            self.calls += 1
            self.assertEqual(params["source"], self.source)
            self.assertTrue(params["include_index"])
            self.assertFalse(params["include_evidence"])
            return {
                "schema": SCHEMA, "mode": "read-only-shadow",
                "source_backend": "sqlite-incremental",
                "source_snapshot_records": len(self.rows),
                "nov_observations": len(self.rows),
                "world_identity_validated": True,
                "checkpoint_watermark_in_snapshot": True,
                "checkpoint_unchanged_during_copy": True,
                "world_mutated": False, "selection_authority": False,
                "central_sync": False, "bdr_used": False,
                "_private_index": deepcopy(self.rows),
            }

        self.load = load
        self.cache = VersionedNovRecallCache(
            source=self.source, world_path=self.world,
            checkpoint_path=self.checkpoint, private_root=self.private,
            _clock=lambda: self.now[0], _loader=self.load,
        )
        self.frame = build_nov_cognitive_frame(
            world={
                "world_id": "nov-test", "current_tick": 20, "version": 1,
                "sequence": 20, "environment": {"period": "day", "weather": "sun"},
            },
            observer={"id": "nov", "type": "human", "region_id": "clearing",
                      "properties": {"needs": {"curiosity": 0.8}}},
            targets={},
        )

    def test_one_snapshot_many_frame_queries_without_rebuild(self):
        first = self.cache(self.frame)
        second = self.cache(self.frame)
        self.assertEqual(self.calls, 1)
        self.assertEqual(first["cache_status"], "refreshed")
        self.assertEqual(second["cache_status"], "hit")
        self.assertEqual(first["historical_matches"], 2)
        self.assertEqual([x["logical_tick"] for x in first["selected"]], [3, 8])
        context = freeze_memory_context(self.frame, first)
        self.assertEqual(context.public_view["evidence_count"], 2)
        self.assertNotIn("live-obs:", json.dumps(context.public_view))
        self.assertNotIn("live-obs:", repr(self.cache))
        self.assertNotIn("synthetic-only", json.dumps(second))
        self.assertEqual(self.source.read_bytes(), b"synthetic-only")

    def test_return_mutation_cannot_poison_cache_index(self):
        prior = self.cache(self.frame)
        prior["private_evidence"][0]["observation"]["need"] = "fabricated"
        subsequent = self.cache(self.frame)
        self.assertEqual(subsequent["private_evidence"][0]["observation"]["need"], "curiosity")
        self.assertEqual(self.calls, 1)

    def test_wal_checkpoint_and_ttl_each_invalidate(self):
        self.cache(self.frame)
        self.wal.write_bytes(b"new append")
        self.assertEqual(self.cache(self.frame)["cache_status"], "refreshed")
        self.checkpoint.write_text(json.dumps({
            "schema": CHECKPOINT_SCHEMA, "world_id": "nov-test", "cursor": 0,
            "revision": 1,
        }))
        self.assertEqual(self.cache(self.frame)["cache_status"], "refreshed")
        self.now[0] = 181.0
        self.assertEqual(self.cache(self.frame)["cache_status"], "refreshed")
        self.assertEqual(self.calls, 4)

    def test_db_replace_and_source_change_during_load_fail_closed(self):
        self.cache(self.frame)
        self.source.unlink()
        self.source.write_bytes(b"replaced")
        self.assertEqual(self.cache(self.frame)["cache_status"], "refreshed")
        self.assertEqual(self.calls, 2)
        self.cache.invalidate()
        original = self.cache._loader
        def moving(**kwargs):
            report = original(**kwargs)
            self.wal.write_bytes(b"changed while validating")
            return report
        self.cache._loader = moving
        with self.assertRaisesRegex(RecallBlocked, "source_moved"):
            self.cache(self.frame)
        self.assertIsNone(self.cache._report)

    def test_change_during_query_rejected(self):
        self.cache(self.frame)
        current = self.cache._current_version
        calls = [0]
        def changing():
            calls[0] += 1
            if calls[0] == 2:
                self.wal.write_bytes(b"changed during query")
            return current()
        self.cache._current_version = changing
        with self.assertRaisesRegex(RecallBlocked, "source_moved_during_query"):
            self.cache(self.frame)
        self.assertIsNone(self.cache._report)

    def test_cross_world_and_future_episode_cannot_leak(self):
        self.rows.append(row("d", 100, "curiosity", "clearing"))
        recent = self.cache(self.frame)
        self.assertTrue(all(x["logical_tick"] <= 20 for x in recent["private_evidence"]))
        self.assertEqual(recent["nov_observations"], 3)
        self.world.write_text(json.dumps({"world_id": "another-world", "environment": {}}))
        self.checkpoint.write_text(json.dumps({
            "schema": CHECKPOINT_SCHEMA, "world_id": "another-world", "cursor": 0,
        }))
        with self.assertRaisesRegex(RecallBlocked, "frame_world_mismatch"):
            self.cache(self.frame)

    def test_empty_memory_never_invents_evidence(self):
        self.rows.clear()
        out = self.cache(self.frame)
        self.assertEqual(out["historical_matches"], 0)
        self.assertEqual(out["private_evidence"], [])
        self.assertEqual(freeze_memory_context(self.frame, out).public_view["evidence_count"], 0)

    def test_oversized_index_and_unverified_report_fail_closed(self):
        self.cache.max_records = 2
        with self.assertRaisesRegex(RecallBlocked, "record_budget"):
            self.cache(self.frame)
        self.cache.max_records = 2048
        self.rows.clear()
        self.rows.append(row("a", 3, "curiosity", "clearing"))
        self.cache._loader = lambda **_: {
            "schema": SCHEMA, "source_backend": "sqlite-incremental",
            "checkpoint_unchanged_during_copy": False,
            "_private_index": self.rows,
        }
        with self.assertRaisesRegex(RecallBlocked, "unverified_snapshot"):
            self.cache(self.frame)

    def test_no_implicit_live_wiring_or_persistence(self):
        main = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertNotIn("VersionedNovRecallCache", main)
        self.assertNotIn("memory_recall_provider=", main)
        self.assertEqual(self.cache._version_loaded, None)
        self.assertFalse(list(self.private.glob("nov-recall-*")))


if __name__ == "__main__":
    unittest.main()
