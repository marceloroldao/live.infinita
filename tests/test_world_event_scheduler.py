from __future__ import annotations

import importlib.util
import json
import os
from unittest.mock import patch
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

clock_module = load("event_clock_test_module", RUNTIME / "simulation_clock.py")
event_module = load("world_event_scheduler_test_module", RUNTIME / "world_event_scheduler.py")
tick_module = load("event_world_tick_test_module", RUNTIME / "world_tick.py")
SimulationClock = clock_module.SimulationClock
WorldEventScheduler = event_module.WorldEventScheduler
WorldTickRunner = tick_module.WorldTickRunner


class FakeGuarded:
    def __init__(self) -> None:
        self.calls = []
        self.reject = False
        self.counter = 0

    def commit(self, operations, *, principal, context=None, narration=""):
        self.calls.append({
            "operations": operations,
            "principal": principal,
            "context": context,
            "narration": narration,
        })
        self.counter += 1
        if self.reject:
            return {
                "ok": False,
                "decision": {"reason": "blocked by test policy"},
                "audit": {"mutation_decision_id": f"dec-{self.counter}"},
                "event": None,
                "world": None,
            }
        return {
            "ok": True,
            "decision": {"reason": "accepted"},
            "audit": {"mutation_decision_id": f"dec-{self.counter}"},
            "event": {"event_id": f"evt-{self.counter}"},
            "world": {"state_hash": f"hash-{self.counter}"},
        }


class EmptyLedger:
    def active(self):
        return []


class EmptyPlanScheduler:
    def __init__(self) -> None:
        self.ledger = EmptyLedger()

    def tick(self, plan_id):
        raise AssertionError("no plan should run")


class RecordingPlanScheduler:
    def __init__(self, order):
        self.order = order
        self.ledger = self

    def active(self):
        return [{"plan_id": "plan_a", "status": "running"}]

    def tick(self, plan_id):
        self.order.append("plan")
        return {
            "status": "running",
            "next_step_index": 1,
            "last_world_event_id": "plan-event",
            "last_mutation_decision_id": "plan-decision",
        }


class OrderedFakeGuarded(FakeGuarded):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def commit(self, *args, **kwargs):
        self.order.append("event")
        return super().commit(*args, **kwargs)


PRINCIPAL = {"source": "scheduler", "actor_id": "world", "authority": "system", "subject_entity_id": None}


class WorldEventSchedulerTest(unittest.TestCase):
    def test_one_shot_event_fires_only_when_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = WorldEventScheduler(Path(tmp) / "events.jsonl", guarded)
            row = scheduler.schedule(
                due_tick=5,
                operations=[{"op": "set_world", "path": ["environment", "weather"], "value": "rain"}],
                principal=PRINCIPAL,
                narration="start rain",
            )
            self.assertEqual(scheduler.fire_due(4), [])
            fired = scheduler.fire_due(5)
            self.assertEqual(len(fired), 1)
            self.assertEqual(fired[0]["status"], "fired")
            self.assertEqual(fired[0]["fire_count"], 1)
            self.assertEqual(fired[0]["last_world_event_id"], "evt-1")
            self.assertEqual(scheduler.fire_due(6), [])
            self.assertEqual(scheduler.get(row["scheduled_event_id"])["status"], "fired")

    def test_recurring_event_advances_due_tick_without_catch_up_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = WorldEventScheduler(Path(tmp) / "events.jsonl", guarded)
            row = scheduler.schedule(
                due_tick=10,
                recurrence_every_ticks=5,
                operations=[{"op": "set_world", "path": ["environment", "period"], "value": "night"}],
                principal=PRINCIPAL,
            )
            first = scheduler.fire_due(100)
            self.assertEqual(len(first), 1)
            current = scheduler.get(row["scheduled_event_id"])
            self.assertEqual(current["fire_count"], 1)
            self.assertEqual(current["due_tick"], 15)
            # One fire_due call fires each scheduled event at most once. A large
            # logical jump never loops to repay missed recurrences.
            self.assertEqual(len(guarded.calls), 1)

    def test_policy_rejection_marks_event_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            guarded.reject = True
            scheduler = WorldEventScheduler(Path(tmp) / "events.jsonl", guarded)
            row = scheduler.schedule(
                due_tick=1,
                operations=[{"op": "remove", "entity_id": "tree"}],
                principal={"source": "npc", "actor_id": "nov", "authority": "observer"},
            )
            result = scheduler.fire_due(1)[0]
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["fire_count"], 0)
            self.assertIn("blocked", result["last_error"])
            self.assertEqual(scheduler.get(row["scheduled_event_id"])["status"], "failed")

    def test_world_tick_fires_events_before_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            order = []
            guarded = OrderedFakeGuarded(order)
            event_scheduler = WorldEventScheduler(Path(tmp) / "events.jsonl", guarded)
            event_scheduler.schedule(
                due_tick=1,
                operations=[{"op": "set_world", "path": ["environment", "weather"], "value": "fog"}],
                principal=PRINCIPAL,
            )
            clock = SimulationClock(Path(tmp) / "clock.json")
            runner = WorldTickRunner(clock, RecordingPlanScheduler(order), event_scheduler)
            result = runner.tick()
            self.assertEqual(order, ["event", "plan"])
            self.assertEqual(result["clock"]["tick"], 1)
            self.assertEqual(len(result["events"]), 1)
            self.assertEqual(len(result["plans"]), 1)

    def test_paused_world_fires_no_due_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            event_scheduler = WorldEventScheduler(Path(tmp) / "events.jsonl", guarded)
            event_scheduler.schedule(
                due_tick=0,
                operations=[{"op": "set_world", "path": ["environment", "period"], "value": "day"}],
                principal=PRINCIPAL,
            )
            clock = SimulationClock(Path(tmp) / "clock.json")
            clock.pause()
            runner = WorldTickRunner(clock, EmptyPlanScheduler(), event_scheduler)
            result = runner.tick()
            self.assertFalse(result["advanced"])
            self.assertEqual(result["events"], [])
            self.assertEqual(guarded.calls, [])


    def test_due_event_view_avoids_history_replay_and_updates_recurring_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            guarded = FakeGuarded()
            scheduler = WorldEventScheduler(path, guarded)
            def schedule(tick, key):
                return scheduler.schedule(
                    due_tick=tick,
                    operations=[{"op": "set_world", "path": ["environment", "period"], "value": key}],
                    principal=PRINCIPAL, idempotency_key=key,
                )
            late = schedule(9, "late")
            first = schedule(2, "early")
            scheduled = scheduler.get(first["scheduled_event_id"])
            with patch.object(scheduler, "history", side_effect=AssertionError("replay on warm view")), \\
                 patch.object(scheduler, "current", side_effect=AssertionError("full copy")):
                self.assertEqual(scheduler.get_by_idempotency_key("early"), scheduled)
                self.assertEqual(scheduler.due(1), [])
                self.assertEqual([r["scheduled_event_id"] for r in scheduler.due(9)],
                                 [first["scheduled_event_id"], late["scheduled_event_id"]])
                self.assertEqual(schedule(2, "early"), scheduled)
                result = scheduler.fire_due(2)
                self.assertEqual(result[0]["status"], "fired")
                self.assertEqual(scheduler.get(first["scheduled_event_id"])["status"], "fired")
                self.assertEqual([r["scheduled_event_id"] for r in scheduler.due(9)],
                                 [late["scheduled_event_id"]])
            external = dict(late, scheduled_event_id="external", due_tick=1, idempotency_key="ext")
            with path.open("ab") as fh:
                fh.write((json.dumps(external) + "\n").encode("utf-8"))
            self.assertEqual([r["scheduled_event_id"] for r in scheduler.due(9)],
                             ["external", late["scheduled_event_id"]])
            replacement = Path(tmp) / "replacement.jsonl"
            replacement.write_text(json.dumps(dict(late, scheduled_event_id="replacement", due_tick=3)) + "\n",
                                   encoding="utf-8")
            os.replace(replacement, path)
            self.assertEqual([r["scheduled_event_id"] for r in scheduler.due(9)], ["replacement"])
            self.assertIsNone(scheduler.get("external"))

    def test_recurring_event_warm_view_preserves_one_fire_per_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = WorldEventScheduler(Path(tmp) / "events.jsonl", FakeGuarded())
            row = scheduler.schedule(
                due_tick=1, recurrence_every_ticks=3,
                operations=[{"op": "set_world", "path": ["environment", "period"], "value": "day"}],
                principal=PRINCIPAL, idempotency_key="period",
            )
            self.assertEqual(len(scheduler.due(1)), 1)
            with patch.object(scheduler, "history", side_effect=AssertionError("warm full replay")):
                first = scheduler.fire_due(30)
                self.assertEqual(len(first), 1)
                self.assertEqual(first[0]["fire_count"], 1)
                self.assertEqual(first[0]["due_tick"], 4)
                self.assertEqual(len(scheduler.fire_due(30)), 1)
                self.assertEqual(scheduler.get_by_idempotency_key("period")["fire_count"], 2)


if __name__ == "__main__":
    unittest.main()
