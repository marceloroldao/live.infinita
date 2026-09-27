from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

clock_module = load("simulation_clock_test_module", RUNTIME / "simulation_clock.py")
tick_module = load("world_tick_test_module", RUNTIME / "world_tick.py")
SimulationClock = clock_module.SimulationClock
WorldTickRunner = tick_module.WorldTickRunner


class FakeLedger:
    def __init__(self) -> None:
        self.rows = [
            {"plan_id": "plan_b", "status": "running"},
            {"plan_id": "plan_a", "status": "running"},
        ]

    def active(self):
        return list(self.rows)


class FakeScheduler:
    def __init__(self) -> None:
        self.ledger = FakeLedger()
        self.calls: list[str] = []

    def tick(self, plan_id: str):
        self.calls.append(plan_id)
        return {
            "plan_id": plan_id,
            "status": "running",
            "next_step_index": 1,
            "last_world_event_id": f"evt-{plan_id}",
            "last_mutation_decision_id": f"dec-{plan_id}",
        }


class SimulationClockWorldTickTest(unittest.TestCase):
    def test_clock_persists_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clock.json"
            clock = SimulationClock(path, tick_duration_ms=500)
            self.assertEqual(clock.state().tick, 0)
            clock.advance()
            reopened = SimulationClock(path, tick_duration_ms=999)
            self.assertEqual(reopened.state().tick, 1)
            self.assertEqual(reopened.state().tick_duration_ms, 500)
            self.assertEqual(reopened.state().as_dict()["logical_time_ms"], 500)

    def test_pause_prevents_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = SimulationClock(Path(tmp) / "clock.json")
            clock.pause()
            before = clock.state().tick
            after = clock.advance()
            self.assertEqual(after.tick, before)
            self.assertTrue(after.paused)

    def test_world_tick_orders_plans_and_runs_once_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = SimulationClock(Path(tmp) / "clock.json")
            scheduler = FakeScheduler()
            runner = WorldTickRunner(clock, scheduler)
            result = runner.tick()
            self.assertTrue(result["advanced"])
            self.assertEqual(result["clock"]["tick"], 1)
            self.assertEqual(scheduler.calls, ["plan_a", "plan_b"])
            self.assertEqual([row["plan_id"] for row in result["plans"]], ["plan_a", "plan_b"])

    def test_paused_world_tick_executes_no_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = SimulationClock(Path(tmp) / "clock.json")
            scheduler = FakeScheduler()
            runner = WorldTickRunner(clock, scheduler)
            clock.pause()
            result = runner.tick()
            self.assertFalse(result["advanced"])
            self.assertEqual(scheduler.calls, [])
            self.assertEqual(result["clock"]["tick"], 0)


    def test_stage_observer_is_passive_and_reports_plan_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = SimulationClock(Path(tmp) / "clock.json")
            scheduler = FakeScheduler()
            samples = []
            now = iter(range(0, 1000000, 1000))
            runner = WorldTickRunner(
                clock,
                scheduler,
                stage_observer=lambda name, ns: samples.append((name, ns)),
                monotonic_ns=lambda: next(now),
            )
            result = runner.tick()
            self.assertTrue(result["advanced"])
            self.assertEqual(result["clock"]["tick"], 1)
            self.assertEqual(scheduler.calls, ["plan_a", "plan_b"])
            names = [name for name, _ in samples]
            self.assertIn("clock.advance", names)
            self.assertIn("plans.arbitrate", names)
            self.assertEqual(names.count("plans.tick"), 2)
            self.assertTrue(all(ns >= 0 for _, ns in samples))


if __name__ == "__main__":
    unittest.main()
