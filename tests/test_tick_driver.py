from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

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


def test_single_writer_lease_excludes_second_writer(tmp_path: Path) -> None:
    path = tmp_path / "world-tick.lock"
    first = SingleWriterTickLease(path, owner_id="first")
    second = SingleWriterTickLease(path, owner_id="second")
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


def test_driver_executes_exactly_one_tick_per_run_once(tmp_path: Path) -> None:
    runner = FakeRunner()
    driver = WorldTickDriver(runner, lease=SingleWriterTickLease(tmp_path / "tick.lock"))
    result = driver.run_once()
    assert result["executed"] is True
    assert runner.calls == 1
    assert runner.clock.state().tick == 1


def test_driver_does_not_catch_up_after_long_downtime(tmp_path: Path) -> None:
    runner = FakeRunner()
    driver = WorldTickDriver(runner, lease=SingleWriterTickLease(tmp_path / "tick.lock"))

    # Simulate any amount of wall-clock downtime by simply not calling the driver.
    # When service resumes there is exactly one next logical tick.
    runner.clock._state.tick = 40
    result = driver.run_once()
    assert result["executed"] is True
    assert runner.calls == 1
    assert runner.clock.state().tick == 41


def test_serve_uses_current_interval_without_accumulated_backlog(tmp_path: Path) -> None:
    runner = FakeRunner()
    now = [100.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        # Simulate a huge delay after every scheduled sleep. The driver must not
        # translate that delay into extra logical ticks.
        now[0] += seconds + 1200.0

    driver = WorldTickDriver(
        runner,
        lease=SingleWriterTickLease(tmp_path / "tick.lock"),
        monotonic=monotonic,
        sleeper=sleeper,
    )
    results = driver.serve(max_ticks=3)
    assert len(results) == 3
    assert runner.calls == 3
    assert runner.clock.state().tick == 3
    assert len(sleeps) == 3
    assert all(value == 0.5 for value in sleeps)
