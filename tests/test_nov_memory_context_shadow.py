"""Opt-in Nov memory-context bridge: provenance, privacy and shadow-only gates."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cognitive_shadow import CognitiveShadowRecorder  # noqa: E402
from memoria_v2_adapter import build_nov_cognitive_frame  # noqa: E402
from nov_memory_context_shadow import (  # noqa: E402
    SCHEMA, MemoryContextRejected, freeze_memory_context,
)
from nov_memory_recall_shadow import SCHEMA as RECALL_SCHEMA  # noqa: E402
from shadow_world_tick import ShadowWorldTickRunner  # noqa: E402
from tests.test_memoria_v2_shadow_mode import FakeStore, FakeRunner  # noqa: E402


def fixture():
    world = {
        "world_id": "nov-test", "current_tick": 20, "version": 10, "sequence": 20,
        "environment": {"weather": "sun", "period": "day"},
    }
    store = FakeStore()
    frame = build_nov_cognitive_frame(
        world=world, observer=store.get_entity("nov"),
        targets={
            key: store.get_entity(key) for key in ("fire_01", "shelter_marker", "ancient_tree")
        },
    )
    key = "a" * 64
    evidence = {
        "record_key": key,
        "evidence_id": "live-obs:" + key[:40],
        "content_sha256": "b" * 64,
        "world_id": "nov-test",
        "provenance": "live.infinita:npc_episode_v1",
        "logical_tick": 11,
        "matching_addresses": ["need", "region_id"],
        "observation": {
            "need": "curiosity", "strategy_id": "nov_explore",
            "context": {"region_id": "clearing", "weather": "sun"},
            "outcome": {"satisfaction": 0.7},
        },
    }
    recall = {
        "schema": RECALL_SCHEMA, "mode": "read-only-shadow",
        "source_backend": "sqlite-incremental",
        "world_identity_validated": True,
        "checkpoint_watermark_in_snapshot": True,
        "checkpoint_unchanged_during_copy": True,
        "source_snapshot_records": 15,
        "historical_matches": 1,
        "selected": [{"logical_tick": 11, "source": "typed_confirmed_nov_outcome",
                      "matched_address_count": 2}],
        "private_evidence": [evidence],
        "selection_authority": False, "world_mutated": False, "central_sync": False,
        "bdr_used": False, "live_caught_up_claim": False,
    }
    return frame, recall, world, store


class MemoryContextContract(unittest.TestCase):
    def test_private_ids_are_available_only_in_process(self):
        frame, recall, _, _ = fixture()
        result = freeze_memory_context(frame, recall)
        self.assertEqual(result.frame_id, frame.frame_id)
        self.assertEqual(result.private_evidence_ids, ("live-obs:" + "a"*40,))
        self.assertEqual(result.public_view["schema"], SCHEMA)
        self.assertFalse(result.public_view["used_to_rank"])
        self.assertFalse(result.public_view["selection_authority"])
        self.assertNotIn("live-obs:", json.dumps(result.public_view))
        self.assertNotIn("content_sha256", json.dumps(result.public_view))
        self.assertNotIn("live-obs:", repr(result))

    def test_empty_verified_recall_is_abstention(self):
        frame, recall, _, _ = fixture()
        recall["private_evidence"] = []
        recall["selected"] = []
        recall["historical_matches"] = 0
        result = freeze_memory_context(frame, recall)
        self.assertEqual(result.private_evidence_ids, ())
        self.assertEqual(result.public_view["evidence_count"], 0)

    def test_corrupt_or_untrusted_recalls_rejected(self):
        frame, good, _, _ = fixture()
        cases = (
            ("schema", "incorrect"),
            ("source_backend", "bdr"),
            ("selection_authority", True),
            ("world_mutated", True),
            ("central_sync", True),
            ("bdr_used", True),
            ("checkpoint_watermark_in_snapshot", False),
            ("source_snapshot_records", 0),
            ("historical_matches", 0),
        )
        for field, value in cases:
            with self.subTest(field=field):
                recall = deepcopy(good)
                recall[field] = value
                with self.assertRaises(MemoryContextRejected):
                    freeze_memory_context(frame, recall)

    def test_cross_world_future_duplicate_or_opaque_address_rejected(self):
        frame, good, _, _ = fixture()
        changes = (
            ("world_id", "another-world"),
            ("logical_tick", 21),
            ("evidence_id", "fabricated"),
            ("matching_addresses", ["need", "text"]),
        )
        for field, value in changes:
            with self.subTest(field=field):
                recall = deepcopy(good)
                recall["private_evidence"][0][field] = value
                with self.assertRaises(MemoryContextRejected):
                    freeze_memory_context(frame, recall)
        recall = deepcopy(good)
        recall["private_evidence"].append(deepcopy(recall["private_evidence"][0]))
        recall["selected"].append(deepcopy(recall["selected"][0]))
        with self.assertRaises(MemoryContextRejected):
            freeze_memory_context(frame, recall)

    def test_shadow_injection_captures_redacted_context_only(self):
        frame, recall, world, store = fixture()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "shadow.jsonl"
            calls = []
            def provider(requested_frame):
                calls.append(requested_frame.frame_id)
                return deepcopy(recall)
            recorder = CognitiveShadowRecorder(
                path, world_provider=lambda: deepcopy(world), store=store,
                enabled=True, memory_recall_provider=provider,
            )
            result = ShadowWorldTickRunner(FakeRunner(world, store), recorder).tick()
            self.assertEqual(result["cognitive_shadow"]["status"], "recorded")
            self.assertEqual(calls, [frame.frame_id])
            saved = path.read_text(encoding="utf-8")
            row = json.loads(saved.strip())
            self.assertEqual(row["memory_recall_context"]["evidence_count"], 1)
            self.assertFalse(row["memory_recall_context"]["used_to_rank"])
            self.assertNotIn("live-obs:", saved)
            self.assertNotIn("content_sha256", saved)
            self.assertEqual(world["version"], 11)

    def test_provider_failure_never_blocks_world_tick(self):
        _, _, world, store = fixture()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(
                path, world_provider=lambda: deepcopy(world), store=store,
                enabled=True, memory_recall_provider=lambda _: (_ for _ in ()).throw(
                    MemoryContextRejected("untrusted_source")
                ),
            )
            output = ShadowWorldTickRunner(FakeRunner(world, store), recorder).tick()
            self.assertTrue(output["advanced"])
            self.assertEqual(output["cognitive_shadow"]["status"], "begin_error")
            self.assertEqual(world["version"], 11)
            self.assertFalse(path.exists())

    def test_production_wiring_is_off(self):
        main = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertNotIn("memory_recall_provider=", main)
        self.assertNotIn("nov_memory_context_shadow", main)
        self.assertNotIn("nov_memory_recall_shadow", main)


if __name__ == "__main__":
    unittest.main()
