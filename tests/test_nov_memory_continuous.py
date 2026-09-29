"""MVP-018L bounded continuous observer; no world-writer or private payload."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from memoria_v2_adapter import CognitiveFrame
from nov_memory_async_prepare import PreparedRead
from nov_memory_continuous import ContinuousOwnerMonitor, RecallBlocked, run


def frame(tick=10):
    return CognitiveFrame(
        frame_id="frame" + str(tick), tick_id=tick,
        observer_id="nov",
        state_addresses=("live:world:test", "live:entity:nov", "live:region:forest"),
        available_interventions=(), candidate_outcomes=(),
        provenance={"authority": "read-only-cognitive-projection"},
    )


class FakeWorker:
    def __init__(self):
        self.status = "not_started"
        self.calls = 0
        self.closed = False

    def start(self):
        self.status = "not_ready"

    def submit(self, value):
        self.calls += 1
        self.status = "pending"
        return "queued"

    def peek(self, value):
        if self.status == "ready":
            return PreparedRead("ready", None, None, {
                "primary_count": 5, "supplementary_count": 3,
                "primary_overlap_counts": [4] * 5,
                "supplementary_overlap_counts": [3] * 3,
            })
        return PreparedRead(self.status, None, None, {"status": self.status})

    def wait_ready(self, value, *, timeout=5.0):
        self.status = "ready"
        return self.peek(value)

    def close(self):
        self.closed = True


class ContinuousMonitorTests(unittest.TestCase):
    def test_coalesces_inflight_and_only_refreshes_after_interval(self):
        now = [0.0]
        worker = FakeWorker()
        worker.start()
        runner = ContinuousOwnerMonitor(
            worker, sampler=lambda: frame(), clock=lambda: now[0],
        )
        first = runner.step()
        self.assertEqual(first["status"], "pending")
        self.assertTrue(first["submitted"])
        now[0] += 1
        second = runner.step()
        self.assertEqual(second["status"], "pending")
        self.assertFalse(second["submitted"])
        self.assertEqual(worker.calls, 1)
        worker.status = "ready"
        third = runner.step()
        self.assertEqual(third["status"], "ready")
        self.assertEqual(third["primary_count"], 5)
        self.assertEqual(third["supplementary_count"], 3)
        now[0] += 4
        fourth = runner.step()
        self.assertEqual(fourth["status"], "pending")
        self.assertEqual(worker.calls, 2)

    def test_bounded_retry_after_pending_timeout(self):
        now = [0.0]
        worker = FakeWorker()
        worker.start()
        runner = ContinuousOwnerMonitor(
            worker, sampler=lambda: frame(), clock=lambda: now[0],
        )
        runner.step()
        now[0] = 9.0
        retry = runner.step()
        self.assertTrue(retry["submitted"])
        self.assertEqual(worker.calls, 2)

    def test_sampler_and_provider_failures_abstain(self):
        worker = FakeWorker()
        worker.start()
        runner = ContinuousOwnerMonitor(
            worker, sampler=lambda: (_ for _ in ()).throw(RecallBlocked("busy")),
        )
        output = runner.step()
        self.assertEqual(output["status"], "frame_unavailable")
        self.assertFalse(output["selection_authority"])
        self.assertEqual(worker.calls, 0)

    def test_canary_has_bounded_cycles_and_redacted_results(self):
        worker = FakeWorker()
        emitted = []
        elapsed = [0.0]
        result = run(
            cycles=4, period=1.0, refresh=4.0, canary=True,
            worker=worker, sampler=lambda: frame(int(elapsed[0]) + 10),
            clock=lambda: elapsed[0],
            sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
            emit=emitted.append,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["cycles"], 4)
        self.assertGreaterEqual(result["ready_reads"], 1)
        self.assertTrue(worker.closed)
        self.assertEqual(len(emitted), 4)
        self.assertFalse(result["main_runtime_wired"])
        self.assertEqual(sum(result["status_counts"].values()), result["samples"])
        self.assertEqual(result["ready_reads"] + result["abstentions"], result["samples"])
        self.assertEqual(result["status_counts"]["ready"], result["ready_reads"])
        self.assertGreaterEqual(result["peak_rss_kib"], 1)
        self.assertLessEqual(result["median_step_ms"], result["max_step_ms"])
        self.assertNotIn("live:world", json.dumps(emitted))
        self.assertNotIn("record_key", json.dumps(emitted))

    def test_production_wiring_off_and_invalid_config_blocked(self):
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertNotIn("nov_memory_continuous", runtime)
        self.assertNotIn("OwnerContinuous", runtime)
        with self.assertRaises(RecallBlocked):
            run(cycles=1, worker=FakeWorker(), sampler=lambda: frame())
        with self.assertRaises(RecallBlocked):
            run(canary=True, worker=FakeWorker(), sampler=lambda: frame())
        with self.assertRaises(RecallBlocked):
            ContinuousOwnerMonitor(FakeWorker(), lambda: frame(), refresh_seconds=0)


if __name__ == "__main__":
    unittest.main()
