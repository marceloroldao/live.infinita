"""Read-only real-world frame projection and bounded owner-side pilot gates."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_live_frame_pilot import (
    OwnerLiveFramePilot, RecallBlocked, read_current_nov_frame,
)
from nov_memory_async_prepare import PreparedRead


class CurrentFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.world = root / "world.json"
        self.cold = root / "cold-store"
        (self.cold / "regions").mkdir(parents=True)
        self.manifest = self.cold / "manifest.json"
        self.region = self.cold / "regions" / (sha256(b"forest").hexdigest() + ".json")
        self.world_data = {
            "world_id": "test-world", "current_tick": 31,
            "sequence": 31, "version": 31, "state_hash": "q",
            "cold_entities": {"mode": "region_file_store"}, "entities": [],
            "environment": {"period": "day", "weather": "sun"},
        }
        self.manifest_data = {
            "version": 1, "entity_region": {"nov": "forest"},
            "region_counts": {"forest": 1}, "entities_total": 1,
        }
        self.region_data = [{
            "id": "nov", "type": "human", "region_id": "forest",
            "properties": {"needs": {"hunger": 0.8}},
        }]
        self.save()

    def save(self):
        self.world.write_text(json.dumps(self.world_data))
        self.manifest.write_text(json.dumps(self.manifest_data))
        self.region.write_text(json.dumps(self.region_data))

    def frame(self):
        return read_current_nov_frame(world_path=self.world, cold_store=self.cold)

    def test_real_nov_region_is_not_assumed_from_world_only(self):
        value = self.frame()
        self.assertEqual(value.tick_id, 31)
        self.assertEqual(value.observer_id, "nov")
        self.assertIn("live:world:test-world", value.state_addresses)
        self.assertIn("live:region:forest", value.state_addresses)
        self.assertIn("live:weather:sun", value.state_addresses)
        self.assertIn("live:need:hunger:high", value.state_addresses)
        self.assertEqual(value.provenance["world_sequence"], 31)

    def test_missing_nov_wrong_region_and_wrong_manifest_fail_closed(self):
        self.manifest_data["entity_region"] = {}
        self.save()
        with self.assertRaises(RecallBlocked):
            self.frame()
        self.manifest_data["entity_region"] = {"nov": "forest"}
        self.region_data[0]["region_id"] = "shelter"
        self.save()
        with self.assertRaises(RecallBlocked):
            self.frame()
        self.region_data[0]["region_id"] = "forest"
        self.manifest_data["version"] = 2
        self.save()
        with self.assertRaises(RecallBlocked):
            self.frame()

    def test_untrusted_world_and_symlink_are_rejected(self):
        self.world_data["cold_entities"]["mode"] = "inline"
        self.save()
        with self.assertRaises(RecallBlocked):
            self.frame()
        self.world_data["cold_entities"]["mode"] = "region_file_store"
        self.save()
        self.region.unlink()
        self.region.symlink_to(self.world)
        with self.assertRaises(RecallBlocked):
            self.frame()

    def test_entity_duplicate_and_oversized_region_fail_closed(self):
        self.region_data.append(deepcopy(self.region_data[0]))
        self.save()
        with self.assertRaises(RecallBlocked):
            self.frame()
        self.region_data = [{"id": "nov", "region_id": "forest",
                             "payload": "x" * (4 * 1024 * 1024)}]
        self.save()
        with self.assertRaises(RecallBlocked):
            self.frame()


class FakePrepared:
    def __init__(self):
        self.started = 0
        self.closed = 0
        self.submitted = []

    def start(self):
        self.started += 1

    def submit(self, frame):
        self.submitted.append(frame.tick_id)

    def peek(self, frame):
        return PreparedRead("ready", None, None, {
            "primary_count": 5, "supplementary_count": 3,
        })

    def close(self):
        self.closed += 1


class TrialTests(unittest.TestCase):
    def test_bounded_trial_uses_later_current_frame_without_raw_data(self):
        from memoria_v2_adapter import CognitiveFrame
        calls = []
        def reader():
            tick = len(calls) + 20
            calls.append(tick)
            return CognitiveFrame(
                frame_id="live" + str(tick), tick_id=tick, observer_id="nov",
                state_addresses=("live:world:x", "live:entity:nov", "live:region:forest"),
                available_interventions=(), candidate_outcomes=(), provenance={},
            )
        clock = [0.0]
        def sleeper(s):
            clock[0] += s
        prepared = FakePrepared()
        result = OwnerLiveFramePilot(
            frame_reader=reader, preparer=prepared, cycles=3, interval=0.5,
            _clock=lambda: clock[0], _sleep=sleeper,
        ).run()
        self.assertEqual(result["cycles"], 3)
        self.assertEqual(result["ready_reads"], 3)
        self.assertEqual(result["distinct_live_frame_ticks"], 6)
        self.assertEqual(result["statuses"], {"ready": 3})
        self.assertEqual(prepared.submitted, [20, 22, 24])
        self.assertEqual((prepared.started, prepared.closed), (1, 1))
        self.assertEqual(result["max_primary_count"], 5)
        self.assertEqual(result["max_supplementary_count"], 3)
        self.assertFalse(result["selection_authority"])
        self.assertTrue(result["actual_live_frame_read"])
        self.assertNotIn("live:world:", json.dumps(result))
        self.assertNotIn("record_key", json.dumps(result))

    def test_failures_abstain_and_close(self):
        counter = [0]
        def broken():
            counter[0] += 1
            raise RecallBlocked("private_other_info")
        prepared = FakePrepared()
        out = OwnerLiveFramePilot(
            frame_reader=broken, preparer=prepared, cycles=2, interval=0.5,
            _clock=lambda: 0.0, _sleep=lambda _: None,
        ).run()
        self.assertEqual(out["ready_reads"], 0)
        self.assertEqual(out["abstained_reads"], 2)
        self.assertEqual(out["statuses"], {"frame_unstable": 2})
        self.assertEqual((prepared.started, prepared.closed), (1, 1))
        self.assertNotIn("private_other_info", json.dumps(out))

    def test_cycle_and_interval_budgets(self):
        for opts in (
            {"cycles": 0}, {"cycles": True}, {"cycles": 61},
            {"interval": 0.1}, {"interval": 10.0}, {"interval": True},
        ):
            with self.subTest(opts=opts), self.assertRaises(RecallBlocked):
                OwnerLiveFramePilot(frame_reader=lambda: None,
                                    preparer=FakePrepared(), **opts)

    def test_never_hooks_into_authoritative_tick(self):
        code = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertNotIn("OwnerLiveFramePilot", code)
        self.assertNotIn("nov_memory_live_frame_pilot", code)
        self.assertNotIn("prepared_memory_provider=", code)


if __name__ == "__main__":
    unittest.main()
