from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from autonomous_runtime import build_authoritative_autonomous_runtime


class NovAutonomousScenarioTest(unittest.TestCase):
    def build(self, root: Path):
        return build_authoritative_autonomous_runtime(
            bootstrap_file=ROOT / "examples" / "world-state.nov-autonomous.bootstrap.json",
            data_dir=root / "data",
            cold_store_dir=root / "cold",
            npc_ids=["nov"],
            tick_duration_ms=500,
        )

    def test_nov_generates_energy_goal_and_reaches_rest_target_without_external_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.build(Path(tmpdir))

            nov_before = runtime.store.get_entity("nov")
            self.assertIsNotNone(nov_before)
            initial_energy = float(nov_before["properties"]["needs"]["energy"])
            self.assertGreaterEqual(initial_energy, 0.85)
            self.assertEqual(nov_before["region_id"], "clearing")
            self.assertEqual(runtime.clock.state().tick, 0)
            self.assertIsNone(runtime.cognition.need_dynamics.get_needs("nov"))

            first = runtime.world_tick.tick()
            self.assertEqual(first["clock"]["tick"], 1)
            dynamic_after_first = runtime.cognition.need_dynamics.get_needs("nov")
            self.assertIsNotNone(dynamic_after_first)
            self.assertEqual(len(first["npc_needs"]), 1)
            self.assertEqual(first["npc_needs"][0]["npc_id"], "nov")
            self.assertEqual(first["npc_needs"][0]["need"], "energy")
            self.assertEqual(first["npc_needs"][0]["status"], "scheduled")
            self.assertTrue(
                first["npc_needs"][0]["plan_id"] or first["npc_needs"][0]["strategy_execution_id"]
            )

            outcomes = list(first["npc_need_outcomes"])
            visited_regions = {runtime.store.get_entity("nov")["region_id"]}
            need_sequence = [row.get("need") for row in first["npc_needs"]]
            for _ in range(12):
                tick = runtime.world_tick.tick()
                outcomes.extend(tick["npc_need_outcomes"])
                need_sequence.extend(row.get("need") for row in tick["npc_needs"])
                nov = runtime.store.get_entity("nov")
                if nov is not None:
                    visited_regions.add(str(nov.get("region_id")))
                if "shelter" in visited_regions and any(row.get("need") == "energy" for row in outcomes):
                    break

            self.assertIn("shelter", visited_regions)
            self.assertTrue(any(row.get("need") == "energy" for row in outcomes))
            self.assertEqual(need_sequence[0], "energy")

            after = runtime.cognition.need_dynamics.get_needs("nov")
            self.assertIsNotNone(after)
            self.assertLess(after["energy"], initial_energy)
            self.assertGreater(runtime.clock.state().tick, 1)

    def test_bootstrap_keeps_autonomy_explicit_to_nov(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.build(Path(tmpdir))
            self.assertEqual(runtime.cognition.need_dynamics.npc_ids, ("nov",))
            self.assertIsNotNone(runtime.store.get_entity("campfire"))
            self.assertIsNotNone(runtime.store.get_entity("bed_nov"))
            self.assertIsNotNone(runtime.store.get_entity("ancient_tree"))

    def test_day_night_schedule_is_idempotent_and_recurring(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = self.build(root)
            scheduled = runtime.event_scheduler.current()
            self.assertEqual(len(scheduled), 2)
            by_bootstrap_id = {
                row["metadata"]["bootstrap_schedule_id"]: row for row in scheduled
            }
            self.assertEqual(by_bootstrap_id["night-cycle"]["due_tick"], 12)
            self.assertEqual(by_bootstrap_id["night-cycle"]["recurrence_every_ticks"], 24)
            self.assertEqual(by_bootstrap_id["day-cycle"]["due_tick"], 24)

            # Rebuilding the same persistent runtime must not duplicate schedules.
            reopened = self.build(root)
            self.assertEqual(len(reopened.event_scheduler.current()), 2)

            for _ in range(12):
                result = reopened.world_tick.tick()
            self.assertEqual(result["clock"]["tick"], 12)
            self.assertEqual(reopened.engine.load_world()["environment"]["period"], "night")
            self.assertEqual(len(result["events"]), 1)

            for _ in range(12):
                result = reopened.world_tick.tick()
            self.assertEqual(result["clock"]["tick"], 24)
            self.assertEqual(reopened.engine.load_world()["environment"]["period"], "day")
            self.assertEqual(len(result["events"]), 1)

            current = {
                row["metadata"]["bootstrap_schedule_id"]: row
                for row in reopened.event_scheduler.current()
            }
            self.assertEqual(current["night-cycle"]["fire_count"], 1)
            self.assertEqual(current["night-cycle"]["due_tick"], 36)
            self.assertEqual(current["day-cycle"]["fire_count"], 1)
            self.assertEqual(current["day-cycle"]["due_tick"], 48)


if __name__ == "__main__":
    unittest.main()
