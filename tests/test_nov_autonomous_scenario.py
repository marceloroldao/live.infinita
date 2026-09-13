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

    def test_nov_generates_energy_goal_reaches_rest_and_remembers_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = self.build(root)

            nov_before = runtime.store.get_entity("nov")
            self.assertIsNotNone(nov_before)
            initial_energy = float(nov_before["properties"]["needs"]["energy"])
            self.assertGreaterEqual(initial_energy, 0.85)
            self.assertEqual(nov_before["region_id"], "clearing")
            self.assertEqual(runtime.clock.state().tick, 0)
            self.assertIsNone(runtime.cognition.need_dynamics.get_needs("nov"))
            self.assertEqual(runtime.cognition.episodic_memory.history(), [])

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

            episodes = runtime.cognition.episodic_memory.recall(
                "nov", need="energy", target_entity_id="bed_nov", limit=5
            )
            self.assertTrue(episodes)
            episode = episodes[0]
            self.assertEqual(episode["need"], "energy")
            self.assertEqual(episode["target_entity_id"], "bed_nov")
            self.assertTrue(
                episode["strategy_id"] == "direct"
                or episode["strategy_id"] == "wait_then_direct"
                or episode["strategy_id"].startswith("via_shelter:")
            )
            self.assertGreater(float(episode["outcome"]["satisfaction"]), 0.0)
            self.assertIsNotNone(episode["logical_tick"])
            self.assertEqual(episode["source"]["kind"], "need_outcome")

            reopened = self.build(root)
            persisted = reopened.cognition.episodic_memory.recall(
                "nov", need="energy", target_entity_id="bed_nov", limit=5
            )
            self.assertEqual([row["episode_id"] for row in persisted], [row["episode_id"] for row in episodes])

    def test_bootstrap_keeps_autonomy_explicit_to_nov(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.build(Path(tmpdir))
            self.assertEqual(runtime.cognition.need_dynamics.npc_ids, ("nov",))
            campfire = runtime.store.get_entity("campfire")
            self.assertIsNotNone(campfire)
            self.assertFalse(campfire["properties"]["lit"])
            self.assertIsNotNone(runtime.store.get_entity("bed_nov"))
            self.assertIsNotNone(runtime.store.get_entity("ancient_tree"))

    def test_day_night_schedule_campfire_and_causal_hypotheses_are_persistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = self.build(root)
            scheduled = runtime.event_scheduler.current()
            conditionals = runtime.conditional_event_scheduler.current()
            self.assertEqual(len(scheduled), 2)
            self.assertEqual(len(conditionals), 2)
            by_bootstrap_id = {
                row["metadata"]["bootstrap_schedule_id"]: row for row in scheduled
            }
            self.assertEqual(by_bootstrap_id["night-cycle"]["due_tick"], 12)
            self.assertEqual(by_bootstrap_id["night-cycle"]["recurrence_every_ticks"], 24)
            self.assertEqual(by_bootstrap_id["day-cycle"]["due_tick"], 24)

            reopened = self.build(root)
            self.assertEqual(len(reopened.event_scheduler.current()), 2)
            self.assertEqual(len(reopened.conditional_event_scheduler.current()), 2)

            for _ in range(11):
                reopened.world_tick.tick()
            before_night = reopened.cognition.need_dynamics.get_needs("nov")
            self.assertIsNotNone(before_night)
            self.assertFalse(reopened.store.get_entity("campfire")["properties"]["lit"])

            result = reopened.world_tick.tick()
            self.assertEqual(result["clock"]["tick"], 12)
            environment = reopened.engine.load_world()["environment"]
            self.assertEqual(environment["period"], "night")
            self.assertAlmostEqual(float(environment["danger_level"]), 0.35)
            self.assertEqual(len(result["events"]), 1)
            self.assertEqual(len(result["causal_observations"]), 1)
            self.assertEqual(result["causal_observations"][0]["support_count"], 1)
            self.assertTrue(reopened.store.get_entity("campfire")["properties"]["lit"])
            self.assertTrue(any(row.get("fire_count") == 1 for row in result["conditional_events"]))
            after_night = reopened.cognition.need_dynamics.get_needs("nov")
            self.assertGreater(after_night["safety"], before_night["safety"])

            night_hypothesis = reopened.cognition.causal_model.hypothesis(
                from_period="day", to_period="night", expected_direction="increase"
            )
            self.assertIsNotNone(night_hypothesis)
            self.assertEqual(night_hypothesis["status"], "provisional")
            self.assertEqual(night_hypothesis["support_count"], 1)

            for _ in range(11):
                reopened.world_tick.tick()
            before_day = reopened.cognition.need_dynamics.get_needs("nov")
            result = reopened.world_tick.tick()
            self.assertEqual(result["clock"]["tick"], 24)
            environment = reopened.engine.load_world()["environment"]
            self.assertEqual(environment["period"], "day")
            self.assertAlmostEqual(float(environment["danger_level"]), 0.05)
            self.assertEqual(len(result["events"]), 1)
            self.assertEqual(len(result["causal_observations"]), 1)
            self.assertFalse(reopened.store.get_entity("campfire")["properties"]["lit"])
            after_day = reopened.cognition.need_dynamics.get_needs("nov")
            self.assertLess(after_day["safety"], before_day["safety"])

            day_hypothesis = reopened.cognition.causal_model.hypothesis(
                from_period="night", to_period="day", expected_direction="decrease"
            )
            self.assertIsNotNone(day_hypothesis)
            self.assertEqual(day_hypothesis["support_count"], 1)

            current = {
                row["metadata"]["bootstrap_schedule_id"]: row
                for row in reopened.event_scheduler.current()
            }
            self.assertEqual(current["night-cycle"]["fire_count"], 1)
            self.assertEqual(current["night-cycle"]["due_tick"], 36)
            self.assertEqual(current["day-cycle"]["fire_count"], 1)
            self.assertEqual(current["day-cycle"]["due_tick"], 48)

            conditional_current = {
                row["metadata"]["bootstrap_conditional_id"]: row
                for row in reopened.conditional_event_scheduler.current()
            }
            self.assertEqual(conditional_current["campfire-on-at-night"]["fire_count"], 1)
            self.assertEqual(conditional_current["campfire-off-at-day"]["fire_count"], 1)

            persisted = self.build(root)
            self.assertEqual(len(persisted.cognition.causal_model.hypotheses()), 2)


if __name__ == "__main__":
    unittest.main()
