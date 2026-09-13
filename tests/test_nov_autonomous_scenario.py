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
    def test_nov_generates_energy_goal_and_reaches_rest_target_without_external_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = build_authoritative_autonomous_runtime(
                bootstrap_file=ROOT / "examples" / "world-state.nov-autonomous.bootstrap.json",
                data_dir=root / "data",
                cold_store_dir=root / "cold",
                npc_ids=["nov"],
                tick_duration_ms=500,
            )

            initial = runtime.cognition.need_dynamics.get_needs("nov")
            self.assertGreaterEqual(initial["energy"], 0.85)
            self.assertEqual(runtime.store.get_entity("nov")["region_id"], "clearing")
            self.assertEqual(runtime.clock.state().tick, 0)

            first = runtime.world_tick.tick()
            self.assertEqual(first["clock"]["tick"], 1)
            self.assertEqual(len(first["npc_needs"]), 1)
            self.assertEqual(first["npc_needs"][0]["npc_id"], "nov")
            self.assertEqual(first["npc_needs"][0]["need"], "energy")
            self.assertEqual(first["npc_needs"][0]["status"], "scheduled")
            self.assertTrue(
                first["npc_needs"][0]["plan_id"] or first["npc_needs"][0]["strategy_execution_id"]
            )

            outcomes = list(first["npc_need_outcomes"])
            for _ in range(12):
                tick = runtime.world_tick.tick()
                outcomes.extend(tick["npc_need_outcomes"])
                nov = runtime.store.get_entity("nov")
                if nov is not None and nov.get("region_id") == "shelter" and outcomes:
                    break

            nov = runtime.store.get_entity("nov")
            self.assertIsNotNone(nov)
            self.assertEqual(nov["region_id"], "shelter")
            self.assertTrue(any(row.get("need") == "energy" for row in outcomes))

            after = runtime.cognition.need_dynamics.get_needs("nov")
            self.assertLess(after["energy"], initial["energy"])
            self.assertGreater(runtime.clock.state().tick, 1)

    def test_bootstrap_keeps_autonomy_explicit_to_nov(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = build_authoritative_autonomous_runtime(
                bootstrap_file=ROOT / "examples" / "world-state.nov-autonomous.bootstrap.json",
                data_dir=root / "data",
                cold_store_dir=root / "cold",
                npc_ids=["nov"],
            )
            self.assertEqual(runtime.cognition.need_dynamics.npc_ids, ("nov",))
            self.assertIsNotNone(runtime.store.get_entity("campfire"))
            self.assertIsNotNone(runtime.store.get_entity("bed_nov"))
            self.assertIsNotNone(runtime.store.get_entity("ancient_tree"))


if __name__ == "__main__":
    unittest.main()
