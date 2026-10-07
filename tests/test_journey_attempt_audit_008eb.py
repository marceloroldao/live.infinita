import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("journey_audit", ROOT / "tools/audit_journey_attempts_008eb.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def records(identity="session:1", reason="arrived"):
    start = {"schema": audit.SCHEMA, "event": "started", "goal_id": identity,
             "world_id": "fixture", "goal": [3, 0], "start": [0, 0], "current": [0, 0],
             "initial_remaining_m": 3, "remaining_m": 3, "started_at_unix": 100,
             "started_monotonic_ms": 1000, "duration_monotonic_ms": 0, "distance_m": 0,
             "quality_eligible": True, "learning_evidence": False, "world_write_authority": False,
             "blocked_attempts": 0, "completed_steps": 0, "causal_ram_steps": 0, "causal_memoria_steps": 0}
    end = dict(start, event="ended", termination=reason, current=[3, 0] if reason=="arrived" else [1, 0],
               remaining_m=0 if reason=="arrived" else 2, ended_at_unix=90,
               ended_monotonic_ms=3500, duration_monotonic_ms=2500,
               distance_m=3 if reason=="arrived" else 1, completed_steps=3,
               quality_eligible=reason=="arrived")
    return start, end

def text(*rows):
    return "\n".join(audit.PREFIX + json.dumps(row) for row in rows)

class JourneyAuditTests(unittest.TestCase):
    def test_arrival_and_interruption_are_separate(self):
        s, e = records()
        s2, e2 = records("session:2", "stuck_recovery")
        result = audit.summarize(text(s, e, s2, e2), now=200)
        self.assertEqual(result["counts"]["arrived"], 1)
        self.assertEqual(result["counts"]["interrupted"], 1)
        self.assertEqual(result["termination_counts"], {"arrived": 1, "stuck_recovery": 1})
        self.assertEqual(result["all_paired_attempts"]["distance_sum_m"], 4)
        self.assertEqual(result["observed_arrival_fraction_among_paired"], .5)
        self.assertFalse(result["memory_advantage_demonstrated"])

    def test_unmatched_records_are_not_failures(self):
        s, _ = records()
        _, e = records("session:2")
        result = audit.summarize(text(s, e))
        self.assertEqual(result["counts"]["open_or_censored"], 1)
        self.assertEqual(result["counts"]["end_without_start_in_window"], 1)
        self.assertEqual(result["counts"]["paired"], 0)
        self.assertIsNone(result["observed_arrival_fraction_among_paired"])
        self.assertIsNone(result["arrivals"]["duration_mean_seconds"])

    def test_duplicates_and_conflicts(self):
        s, e = records()
        result = audit.summarize(text(s, e, s, e))
        self.assertEqual(result["counts"]["paired"], 1)
        self.assertEqual(result["counts"]["identical_duplicates_ignored"], 2)
        altered = dict(e, distance_m=4)
        with self.assertRaises(ValueError):
            audit.summarize(text(s, e, altered))

    def test_bad_authority_numbers_missing_fields(self):
        s, _ = records()
        for key, value in [("world_write_authority", True), ("learning_evidence", True),
                           ("distance_m", float("nan")), ("duration_monotonic_ms", True),
                           ("quality_eligible", 1), ("start", [False, 0])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit.summarize(text(dict(s, **{key: value})))
        missing = dict(s)
        del missing["initial_remaining_m"]
        with self.assertRaises(ValueError):
            audit.summarize(text(missing))

    def test_clock_correction_does_not_change_duration(self):
        s, e = records()
        s["duration_monotonic_ms"] = 1 # Snapshot can occur just after begin.
        result = audit.summarize(text(s, e))
        self.assertEqual(result["arrivals"]["duration_mean_seconds"], 2.5)
        for row in [dict(e, ended_monotonic_ms=999),
                    dict(e, ended_monotonic_ms=3600),
                    dict(e, remaining_m=1),
                    dict(e, termination="invented")]:
            with self.assertRaises(ValueError):
                audit.summarize(text(s, row))

    def test_metadata_quality_and_world_pairing(self):
        s, e = records()
        for row in [dict(e, started_at_unix=101), dict(e, goal=[4, 0]),
                    dict(e, termination="goal_hard_timeout"),
                    dict(e, causal_ram_steps=4)]:
            with self.assertRaises(ValueError):
                audit.summarize(text(s, row))
        e["world_id"] = "other"
        result = audit.summarize(text(s, e))
        self.assertEqual(result["counts"]["paired"], 0)

    def test_empty_noise_and_limits(self):
        self.assertEqual(audit.summarize("NOV_JOURNEY_COMPLETE old\nnoise")["counts"]["paired"], 0)
        s, _ = records()
        original = audit.MAX_EVENTS
        try:
            audit.MAX_EVENTS = 1
            with self.assertRaises(ValueError):
                audit.summarize(text(s, s))
        finally:
            audit.MAX_EVENTS = original
        with self.assertRaises(ValueError):
            audit.summarize(audit.PREFIX + "{bad json")
        with self.assertRaises(ValueError):
            audit.summarize("x" * (audit.MAX_BYTES+1))

if __name__ == "__main__":
    unittest.main()
