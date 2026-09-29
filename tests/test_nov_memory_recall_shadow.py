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

RUNTIME = Path(__file__).resolve().parents[1] / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))
MODULE = RUNTIME / "nov_memory_recall_shadow.py"
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
        checkpoint_bytes = self.checkpoint.read_bytes()
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
        self.assertNotIn("private_evidence", out)
        private = nov.recall_once(
            source=self.source, world_path=self.world,
            checkpoint_path=self.checkpoint, private_root=self.mem,
            include_evidence=True,
        )
        self.assertEqual(private["private_evidence"][0]["observation"]["need"], "hunger")
        self.assertEqual(private["private_evidence"][0]["provenance"], "live.infinita:npc_episode_v1")
        self.assertEqual(len(private["private_evidence"][0]["record_key"]), 64)
        # End-to-end: a real rehydrated EvidenceCore receipt can supply the
        # private, provenance-verified context for the existing shadow frame.
        from memoria_v2_adapter import build_nov_cognitive_frame
        from nov_memory_context_shadow import freeze_memory_context
        frame = build_nov_cognitive_frame(
            world={"world_id": "nov-test", "current_tick": 20, "sequence": 20,
                   "environment": {"period": "day", "weather": "sun"}},
            observer={"id": "nov", "region_id": "forest", "type": "human",
                      "properties": {"needs": {"hunger": 0.8}}},
            targets={},
        )
        context = freeze_memory_context(frame, private)
        self.assertEqual(context.public_view["evidence_count"], 2)
        self.assertFalse(context.public_view["used_to_rank"])
        self.assertNotIn("live-obs:", json.dumps(context.public_view))
        self.assertEqual(self.store.count, original_count)
        self.assertEqual(self.world.read_text()[:1], "{")
        self.assertEqual(self.checkpoint.read_bytes(), checkpoint_bytes)
        self.assertFalse(list(self.mem.glob("nov-recall-*")))
        self.assertEqual(first["record_key"] in (last["record_key"],), False)

    def test_real_v2_separate_owner_scratch_without_private_root_writes(self) -> None:
        from functools import partial
        from memoria_v2_adapter import build_nov_cognitive_frame
        from nov_memory_recall_cache import VersionedNovRecallCache
        self.append("p1", 3, "hunger")
        last = self.append("p2", 5, "hunger")
        self.watermark(last)
        before_source = self.source.read_bytes()
        before_checkpoint = self.checkpoint.read_bytes()
        scratch = Path(self.temp.name) / "owner-scratch"
        scratch.mkdir(mode=0o700)
        frame = build_nov_cognitive_frame(
            world={"world_id": "nov-test", "current_tick": 20, "sequence": 20,
                   "environment": {"period": "day", "weather": "sun"}},
            observer={"id": "nov", "region_id": "forest", "type": "human",
                      "properties": {"needs": {"hunger": 0.8}}}, targets={},
        )
        # Removing parent write permission simulates the read-only source
        # for an unprivileged test user; scratch remains owner-only elsewhere.
        self.mem.chmod(0o500)
        try:
            cache = VersionedNovRecallCache(
                source=self.source, world_path=self.world,
                checkpoint_path=self.checkpoint, private_root=self.mem,
                _loader=partial(nov.recall_once, scratch_root=scratch),
            )
            out = cache(frame)
            self.assertEqual(out["source_snapshot_records"], 2)
            self.assertEqual(out["cache_status"], "refreshed")
        finally:
            self.mem.chmod(0o700)
        self.assertFalse(list(scratch.glob("nov-recall-*")))
        self.assertFalse(list(self.mem.glob("nov-recall-*")))
        self.assertEqual(self.checkpoint.read_bytes(), before_checkpoint)
        self.assertEqual(self.source.read_bytes(), before_source)
        self.assertEqual(self.store.count, 2)

    def test_invalid_scratch_permissions_and_nested_source_fail_closed(self) -> None:
        last = self.append("p1", 3, "hunger")
        self.watermark(last)
        scratch = Path(self.temp.name) / "owner-scratch"
        scratch.mkdir(mode=0o700)
        scratch.chmod(0o777)
        with self.assertRaisesRegex(nov.RecallBlocked, "snapshot_scratch_permissions"):
            nov.recall_once(
                source=self.source, checkpoint_path=self.checkpoint,
                world_path=self.world, private_root=self.mem,
                scratch_root=scratch,
            )
        scratch.chmod(0o700)
        nested = self.mem / "scratch"
        nested.mkdir(mode=0o700)
        with self.assertRaisesRegex(nov.RecallBlocked, "snapshot_scratch_in_private_root"):
            nov.recall_once(
                source=self.source, checkpoint_path=self.checkpoint,
                world_path=self.world, private_root=self.mem,
                scratch_root=nested,
            )
        link = Path(self.temp.name) / "link"
        link.symlink_to(scratch, target_is_directory=True)
        with self.assertRaisesRegex(nov.RecallBlocked, "snapshot_scratch_invalid"):
            nov.recall_once(
                source=self.source, checkpoint_path=self.checkpoint,
                world_path=self.world, private_root=self.mem,
                scratch_root=link,
            )

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

    def test_real_v2_cache_reuses_then_rebuilds_on_durable_ack(self) -> None:
        from memoria_v2_adapter import build_nov_cognitive_frame
        from nov_memory_recall_cache import VersionedNovRecallCache
        from nov_memory_context_shadow import freeze_memory_context
        self.append("p1", 3, "hunger")
        self.append("p2", 5, "thirst")
        last = self.append("p3", 9, "hunger")
        self.watermark(last)
        frame = build_nov_cognitive_frame(
            world={"world_id": "nov-test", "current_tick": 20, "sequence": 20,
                   "environment": {"period": "day", "weather": "sun"}},
            observer={"id": "nov", "region_id": "forest", "type": "human",
                      "properties": {"needs": {"hunger": 0.8}}},
            targets={},
        )
        cache = VersionedNovRecallCache(
            source=self.source, world_path=self.world,
            checkpoint_path=self.checkpoint, private_root=self.mem,
        )
        first = cache(frame)
        self.assertEqual(first["cache_status"], "refreshed")
        self.assertEqual(first["source_snapshot_records"], 3)
        self.assertEqual(first["private_evidence"][0]["observation"]["need"], "hunger")
        self.assertEqual(cache(frame)["cache_status"], "hit")
        self.assertEqual(freeze_memory_context(frame, first).public_view["evidence_count"], 2)
        self.assertFalse(list(self.mem.glob("nov-recall-*")))
        self.assertEqual(self.store.count, 3)
        newer = self.append("p4", 11, "hunger")
        self.watermark(newer)
        updated = cache(frame)
        self.assertEqual(updated["cache_status"], "refreshed")
        self.assertEqual(updated["source_snapshot_records"], 4)
        self.assertEqual(updated["private_evidence"][0]["logical_tick"], 9)
        self.assertEqual(self.store.count, 4)
        self.assertFalse(list(self.mem.glob("nov-recall-*")))

    def test_real_v2_redacted_diagnostics(self) -> None:
        from nov_memory_diagnostics import diagnose, SCHEMA as DIAGNOSTICS_SCHEMA
        self.append("p1", 3, "hunger")
        self.append("p2", 5, "thirst")
        last = self.append("p3", 9, "hunger")
        self.watermark(last)
        before_checkpoint = self.checkpoint.read_bytes()
        before_world = self.world.read_bytes()
        result = diagnose(
            source=self.source, checkpoint=self.checkpoint,
            world=self.world, private_root=self.mem, samples=3,
        )
        self.assertEqual(result["schema"], DIAGNOSTICS_SCHEMA)
        self.assertEqual(result["snapshot_records"], 3)
        self.assertEqual(result["nov_observations"], 3)
        self.assertEqual(result["warm_queries"], 3)
        self.assertEqual(result["distinct_address_values"]["need"], 2)
        self.assertEqual(result["distinct_episode_signatures"], 2)
        self.assertEqual(result["trajectory_distribution"]["unique_observed_outcome_profiles"], 1)
        self.assertEqual(result["trajectory_distribution"]["unique_observed_trajectory_profiles"], 2)
        self.assertEqual(result["trajectory_recall_comparison"]["matching_records"], 2)
        self.assertEqual(result["trajectory_recall_comparison"]["baseline"]["retrieved_count"], 2)
        self.assertEqual(result["trajectory_recall_comparison"]["diversified"]["retrieved_count"], 2)
        self.assertFalse(result["trajectory_recall_comparison"]["selection_authority"])
        self.assertFalse(result["trajectory_recall_comparison"]["new_evidence_created"])
        hybrid = result["hybrid_recall_comparison"]
        self.assertTrue(hybrid["relevance_vector_preserved"])
        self.assertEqual(hybrid["baseline_overlap_counts"], hybrid["hybrid_overlap_counts"])
        self.assertEqual(hybrid["baseline_full_matches"], hybrid["hybrid_full_matches"])
        self.assertEqual(hybrid["matching_records"], result["historical_matches"])
        dual = result["dual_lane_comparison"]
        self.assertEqual(dual["primary_count_unchanged"], hybrid["hybrid_retrieved"])
        self.assertEqual(dual["hybrid_overlap_counts"], hybrid["hybrid_overlap_counts"])
        self.assertEqual(dual["supplementary_count"], len(dual["supplementary_overlap_counts"]))
        self.assertFalse(dual["supplementary_used_to_rank_primary"])
        self.assertFalse(dual["selection_authority"])
        asynchronous = result["async_preparation"]
        self.assertEqual(asynchronous["status"], "ready")
        self.assertEqual(asynchronous["primary_count"], hybrid["hybrid_retrieved"])
        self.assertEqual(asynchronous["supplementary_count"], dual["supplementary_count"])
        self.assertEqual(asynchronous["primary_overlap_counts"], hybrid["hybrid_overlap_counts"])
        self.assertEqual(asynchronous["supplementary_overlap_counts"],
                         dual["supplementary_overlap_counts"])
        self.assertEqual(asynchronous["peek_queries"], 3)
        self.assertTrue(asynchronous["source_rebuild_off_tick"])
        self.assertFalse(asynchronous["main_runtime_wired"])
        self.assertFalse(asynchronous["live_caught_up_claim"])
        self.assertEqual(hybrid["hybrid_retrieved"], result["retrieved_evidence_count"])
        self.assertGreaterEqual(hybrid["hybrid_trajectory_profiles"],
                                hybrid["baseline_trajectory_profiles"])
        self.assertFalse(hybrid["selection_authority"])
        self.assertFalse(hybrid["causal_inference_claim"])
        self.assertTrue(result["checkpoint_stable"])
        self.assertFalse(result["selection_authority"])
        self.assertFalse(result["world_mutated"])
        self.assertFalse(result["live_nov_state_measured"])
        self.assertNotIn("record_key", json.dumps(result))
        self.assertNotIn("live-obs:", json.dumps(result))
        self.assertEqual(self.checkpoint.read_bytes(), before_checkpoint)
        self.assertEqual(self.world.read_bytes(), before_world)
        self.assertEqual(self.store.count, 3)
        self.assertFalse(list(self.mem.glob("nov-recall-*")))

    def test_real_v2_primary_and_supplementary_are_separate(self) -> None:
        from nov_memory_diagnostics import retrospective_frame
        from nov_memory_dual_lane_shadow import OwnerDualLaneRecallObserver
        from nov_memory_recall_cache import VersionedNovRecallCache
        self.append("p1", 1, "thirst")
        self.append("p2", 2, "hunger", region="shelter")
        for index in range(3, 9):
            receipt = self.append("p" + str(index), index, "hunger")
        self.watermark(receipt)
        before_checkpoint = self.checkpoint.read_bytes()
        before_world = self.world.read_bytes()
        _, doc = nov._read_bounded_json(self.world, nov.MAX_WORLD_BYTES, "world")
        frame = retrospective_frame(doc, [
            {"record_key": receipt["record_key"], "logical_tick": 8,
             "addresses": {"need": "hunger", "region_id": "forest"}},
        ])
        cache = VersionedNovRecallCache(
            source=self.source, world_path=self.world,
            checkpoint_path=self.checkpoint, private_root=self.mem,
        )
        primary, supplement, metrics = OwnerDualLaneRecallObserver(cache).refresh(frame)
        self.assertEqual(primary["source_snapshot_records"], 8)
        self.assertEqual([r["matched_address_count"] for r in primary["selected"]],
                         [4, 4, 4, 4, 4])
        self.assertEqual([r["matched_address_count"] for r in supplement["selected"]],
                         [3, 3])
        self.assertEqual(metrics["primary_count_unchanged"], 5)
        self.assertEqual(metrics["supplementary_count"], 2)
        self.assertEqual(metrics["combined_distinct_observed_profiles"], 3)
        self.assertFalse(metrics["selection_authority"])
        self.assertFalse(metrics["supplementary_used_to_rank_primary"])
        self.assertFalse(metrics["new_evidence_created"])
        primary_ids = {row["record_key"] for row in primary["private_evidence"]}
        additional_ids = {row["record_key"] for row in supplement["private_evidence"]}
        self.assertFalse(primary_ids & additional_ids)
        self.assertEqual(self.checkpoint.read_bytes(), before_checkpoint)
        self.assertEqual(self.world.read_bytes(), before_world)
        self.assertEqual(self.store.count, 8)
        self.assertFalse(list(self.mem.glob("nov-recall-*")))

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
