"""Asynchronous owner-only preparation: no blocking source access on read."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from threading import Event, RLock, current_thread
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from memoria_v2_adapter import CognitiveFrame
from nov_memory_async_prepare import OwnerAsyncDualLanePreparation, RecallBlocked


class Version:
    world_id = "w"


class Source:
    def __init__(self):
        self.version = Version()
        self.calls = 0
        self._lock = RLock()
        self._validated_index = [{
            "record_key": "a" * 64, "logical_tick": 3,
            "addresses": {"need": "hunger", "region_id": "forest"},
        }, {
            "record_key": "b" * 64, "logical_tick": 5,
            "addresses": {"need": "hunger", "region_id": "forest"},
        }]

    def _current_version(self):
        if current_thread().name != "nov-memory-owner-prepare":
            raise AssertionError("private file version read in consumer thread")
        self.calls += 1
        return self.version


def record(letter, tick):
    key = letter * 64
    return {
        "record_key": key,
        "evidence_id": "live-obs:" + key[:40],
        "content_sha256": key,
        "logical_tick": tick,
        "observation": {"need": "hunger", "outcome": {"satisfaction": 0.5}},
        "matching_addresses": ["need", "region_id"],
        "provenance": "live.infinita:npc_episode_v1",
        "world_id": "w",
    }


def recall(letter, tick):
    evidence = record(letter, tick)
    return {
        "schema": "live-infinita-nov-local-recall-shadow/v1",
        "mode": "read-only-shadow",
        "source_backend": "sqlite-incremental",
        "source_snapshot_records": 2,
        "historical_matches": 2,
        "selected": [{"logical_tick": tick, "matched_address_count": 2,
                      "source": "typed_confirmed_nov_outcome"}],
        "private_evidence": [evidence],
        "world_identity_validated": True,
        "checkpoint_watermark_in_snapshot": True,
        "checkpoint_unchanged_during_copy": True,
        "selection_authority": False,
        "world_mutated": False,
        "central_sync": False,
        "bdr_used": False,
        "live_caught_up_claim": False,
    }


def frame(tick=10, region="forest", world="w"):
    return CognitiveFrame(
        frame_id="frame-" + str(tick) + "-" + region,
        tick_id=tick, observer_id="nov",
        state_addresses=("live:world:" + world, "live:entity:nov",
                         "live:region:" + region),
        available_interventions=(), candidate_outcomes=(),
        provenance={"authority": "read-only-cognitive-projection"},
    )


class Observer:
    def __init__(self):
        self.calls = 0
        self.block = None

    def refresh(self, value):
        self.calls += 1
        if self.block is not None:
            self.block.wait(timeout=2)
        return recall("a", 3), recall("b", 5), {
            "primary_count_unchanged": 1,
            "supplementary_count": 1,
        }


class AsyncReadTests(unittest.TestCase):
    def setUp(self):
        self.source = Source()
        self.observer = Observer()
        self.worker = OwnerAsyncDualLanePreparation(
            self.source, _observer=self.observer,
            max_age_seconds=6, watch_interval_seconds=0.1,
        )
        self.addCleanup(self.worker.close)

    def ready(self):
        self.worker.start()
        self.assertEqual(self.worker.submit(frame()), "queued")
        result = self.worker.wait_ready(frame(), timeout=2)
        self.assertEqual(result.status, "ready", result.public)
        return result

    def test_off_thread_validation_and_no_file_io_on_peek(self):
        result = self.ready()
        count = self.source.calls
        self.assertEqual(result.public["primary_count"], 1)
        self.assertEqual(result.public["supplementary_count"], 1)
        self.assertEqual(result.public["primary_overlap_counts"], [2])
        self.assertTrue(result.public["historical_snapshot_only"])
        self.assertFalse(result.public["live_caught_up_claim"])
        self.assertFalse(result.public["selection_authority"])
        self.assertEqual(self.worker.peek(frame()).status, "ready")
        self.assertGreaterEqual(self.source.calls, count)
        self.assertNotIn("live-obs:", json.dumps(result.public))
        self.assertNotIn("a" * 64, repr(result))
        self.assertEqual(self.observer.calls, 1)

    def test_frame_lag_regression_and_context_change_abstain(self):
        self.ready()
        self.assertEqual(self.worker.peek(frame(9)).status, "frame_regressed")
        self.assertEqual(self.worker.peek(frame(31)).status, "frame_lagged")
        self.assertEqual(self.worker.peek(frame(11, "shelter")).status, "query_changed")
        self.assertEqual(self.worker.peek(frame(11, world="other")).status, "world_changed")
        self.assertEqual(self.worker.peek(frame(11)).status, "ready")

    def test_age_expiration_and_close_are_fail_closed(self):
        self.ready()
        self.worker._clock = lambda: 1e12
        expired = self.worker.peek(frame())
        self.assertEqual(expired.status, "expired")
        self.assertIsNone(expired.primary)
        self.worker.close()
        self.assertEqual(self.worker.peek(frame()).status, "closed")
        with self.assertRaises(RecallBlocked):
            self.worker.submit(frame())

    def test_background_change_invalidates_old_snapshot(self):
        self.ready()
        self.source.version = Version()
        end = time.monotonic() + 2.0
        while self.worker.peek(frame()).status != "source_changed" and time.monotonic() < end:
            time.sleep(0.01)
        result = self.worker.peek(frame())
        self.assertEqual(result.status, "source_changed")
        self.assertIsNone(result.primary)

    def test_later_request_supersedes_pending(self):
        gate = Event()
        self.observer.block = gate
        self.worker.start()
        self.worker.submit(frame(10))
        # A newer frame supersedes any incomplete earlier request.
        self.worker.submit(frame(11))
        gate.set()
        result = self.worker.wait_ready(frame(11), timeout=2)
        self.assertEqual(result.status, "ready")
        self.assertEqual(self.worker.peek(frame(9)).status, "frame_regressed")

    def test_owner_failure_categories_are_fixed_and_never_expose_exception(self):
        class DeniedObserver:
            def refresh(self, frame):
                raise PermissionError("sensitive-private-path-should-not-appear")
        self.worker._observer = DeniedObserver()
        self.worker.start()
        self.worker.submit(frame())
        result = self.worker.wait_ready(frame(), timeout=2)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.public["blocked_reason"], "permission_denied")
        self.assertNotIn("sensitive-private-path", json.dumps(result.public))
        self.assertIsNone(result.primary)
        self.assertIsNone(result.supplementary)

    def test_invalid_configuration_and_no_automatic_live_hook(self):
        for options in (
            {"max_age_seconds": 0},
            {"max_age_seconds": True},
            {"max_frame_lag_ticks": -1},
            {"watch_interval_seconds": 0},
        ):
            with self.subTest(options=options), self.assertRaises(RecallBlocked):
                OwnerAsyncDualLanePreparation(self.source, _observer=self.observer, **options)
        with self.assertRaises(RecallBlocked):
            self.worker.submit(frame())
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertNotIn("OwnerAsyncDualLanePreparation", runtime)
        self.assertNotIn("nov_memory_async_prepare", runtime)
        self.assertNotIn("memory_recall_provider=", runtime)


if __name__ == "__main__":
    unittest.main()
