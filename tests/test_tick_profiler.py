from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tick_driver_main import build_driver
from tick_profiler import WorldTickProfiler


class FakeClock:
    def state(self):
        return type("State", (), {"tick_duration_ms": 500})()


class FakeRunner:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.calls = 0
        self.stage_observer = None

    def tick(self):
        self.calls += 1
        if self.stage_observer:
            self.stage_observer("fake_stage", 42_000_000)
        return {"advanced": True, "clock": {"tick": self.calls}}


class TickProfilerTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_bounded_profile_and_atomic_report_without_payloads(self) -> None:
        path = self.root / "profile.json"
        profiler = WorldTickProfiler(path, window=2, report_every=2)
        for elapsed in (0.2, 0.6, 0.4):
            profiler.observe_stage("clock", 10_000_000)
            profiler.observe_stage("clock", 20_000_000)
            profiler.observe_stage("plans", 4_000_000)
            profiler.observe_tick({
                "elapsed_seconds": elapsed, "interval_seconds": 0.5,
                "over_budget": elapsed > 0.5, "executed": True,
            })
        snapshot = profiler.snapshot()
        self.assertEqual(snapshot["window_samples"], 2)
        self.assertEqual(snapshot["total_observed_ticks"], 3)
        self.assertEqual(snapshot["over_budget_ticks"], 1)
        self.assertEqual(snapshot["stages"]["clock"]["p95_ms"], 30.0)
        self.assertEqual(snapshot["total"]["p95_ms"], 600.0)
        self.assertEqual(snapshot["unaccounted"]["p50_ms"], 366.0)
        self.assertTrue(path.exists())
        self.assertFalse(path.with_name(path.name + ".tmp").exists())
        saved = json.loads(path.read_text())
        self.assertEqual(saved["total_observed_ticks"], 2)
        self.assertNotIn("payload", path.read_text())

    def test_disabled_profiler_does_not_modify_runner(self) -> None:
        runner = FakeRunner()
        with patch.dict(os.environ, {"LIVE_INFINITA_TICK_PROFILER": "0"}):
            driver = build_driver(runner, self.root)
        self.assertIsNone(runner.stage_observer)
        self.assertIsNone(driver.tick_observer)
        self.assertFalse((self.root / "world-tick-profile.json").exists())

    def test_enabled_profiler_on_shadow_wrapper_is_observational(self) -> None:
        authoritative = FakeRunner()
        class Wrapper:
            def __init__(self, inner):
                self.runner = inner
                self.clock = inner.clock
            def tick(self):
                return self.runner.tick()
        wrapper = Wrapper(authoritative)
        with patch.dict(os.environ, {"LIVE_INFINITA_TICK_PROFILER": "1"}):
            driver = build_driver(wrapper, self.root)
        self.assertIsNotNone(authoritative.stage_observer)
        self.assertIsNotNone(driver.tick_observer)
        driver.tick_observer({
            "elapsed_seconds": 0.075,
            "interval_seconds": 0.5,
            "executed": True,
        })
        self.assertEqual(authoritative.calls, 0)
        self.assertEqual(driver.tick_observer.__self__.snapshot()["window_samples"], 1)


if __name__ == "__main__":
    unittest.main()
