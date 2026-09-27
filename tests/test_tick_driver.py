from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tick_driver import SingleWriterTickLease, WorldTickDriver


class FakeClockState:
    def __init__(self, tick: int = 0, tick_duration_ms: int = 500, paused: bool = False) -> None:
        self.tick = tick
        self.tick_duration_ms = tick_duration_ms
        self.paused = paused


class FakeClock:
    def __init__(self) -> None:
        self._state = FakeClockState()

    def state(self):
        return self._state


class FakeRunner:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.calls = 0

    def tick(self):
        self.calls += 1
        self.clock._state.tick += 1
        return {"advanced": True, "clock": {"tick": self.clock._state.tick}, "plans": []}


class TickDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_single_writer_lease_excludes_second_writer(self) -> None:
        path = self.tmp / "world-tick.lock"
        first = SingleWriterTickLease(path, owner_id="first")
        second = SingleWriterTickLease(path, owner_id="second")
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_driver_executes_exactly_one_tick_per_run_once(self) -> None:
        runner = FakeRunner()
        driver = WorldTickDriver(runner, lease=SingleWriterTickLease(self.tmp / "tick.lock"))
        result = driver.run_once()
        self.assertTrue(result["executed"])
        self.assertEqual(runner.calls, 1)
        self.assertEqual(runner.clock.state().tick, 1)

    def test_driver_does_not_catch_up_after_long_downtime(self) -> None:
        runner = FakeRunner()
        driver = WorldTickDriver(runner, lease=SingleWriterTickLease(self.tmp / "tick.lock"))
        runner.clock._state.tick = 40
        result = driver.run_once()
        self.assertTrue(result["executed"])
        self.assertEqual(runner.calls, 1)
        self.assertEqual(runner.clock.state().tick, 41)

    def test_serve_uses_current_interval_without_accumulated_backlog(self) -> None:
        runner = FakeRunner()
        now = [100.0]
        sleeps: list[float] = []

        def sleeper(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds + 1200.0

        driver = WorldTickDriver(
            runner,
            lease=SingleWriterTickLease(self.tmp / "tick.lock"),
            monotonic=lambda: now[0],
            sleeper=sleeper,
        )
        results = driver.serve(max_ticks=3)
        self.assertEqual(len(results), 3)
        self.assertEqual(runner.calls, 3)
        self.assertEqual(runner.clock.state().tick, 3)
        self.assertEqual(sleeps, [0.5, 0.5, 0.5])

    def test_tick_observer_reports_budget_without_changing_cadence(self) -> None:
        runner = FakeRunner()
        now = [0.0]
        sleeps: list[float] = []
        samples: list[dict] = []

        def monotonic() -> float:
            value = now[0]
            now[0] += 0.3
            return value

        driver = WorldTickDriver(
            runner,
            lease=SingleWriterTickLease(self.tmp / "tick.lock"),
            monotonic=monotonic,
            sleeper=sleeps.append,
            tick_observer=samples.append,
        )
        driver.serve(max_ticks=1)
        self.assertEqual(runner.calls, 1)
        self.assertEqual(len(samples), 1)
        self.assertAlmostEqual(samples[0]["elapsed_seconds"], 0.3)
        self.assertAlmostEqual(samples[0]["interval_seconds"], 0.5)
        self.assertFalse(samples[0]["over_budget"])
        self.assertAlmostEqual(sleeps[0], 0.2)

    def test_tick_observer_failure_cannot_kill_world(self) -> None:
        runner = FakeRunner()

        def broken(_sample: dict) -> None:
            raise RuntimeError("metrics failed")

        driver = WorldTickDriver(
            runner,
            lease=SingleWriterTickLease(self.tmp / "tick.lock"),
            sleeper=lambda _: None,
            tick_observer=broken,
        )
        driver.serve(max_ticks=2)
        self.assertEqual(runner.calls, 2)
        self.assertEqual(runner.clock.state().tick, 2)


if __name__ == "__main__":
    unittest.main()
