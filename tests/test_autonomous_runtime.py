from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from autonomous_runtime import build_authoritative_autonomous_runtime, region_catalog_from_world


class AutonomousRuntimeTest(unittest.TestCase):
    def _bootstrap(self, root: Path) -> Path:
        path = root / "bootstrap.json"
        path.write_text(json.dumps({
            "world_id": "test-world",
            "version": 1,
            "environment": {"period": "day", "weather": "clear"},
            "regions": [
                {"id": "r0", "center": {"x": 0, "y": 0}, "radius": 10, "neighbors": ["r1"]},
                {"id": "r1", "center": {"x": 20, "y": 0}, "radius": 10, "neighbors": ["r0"]},
            ],
            "entities": [
                {
                    "id": "npc", "type": "human", "region_id": "r0",
                    "position": {"x": 0, "y": 0},
                    "properties": {
                        "needs": {"energy": 0.9},
                        "rest_target_entity_id": "bed",
                    },
                },
                {
                    "id": "bed", "type": "place", "region_id": "r1",
                    "position": {"x": 20, "y": 0},
                    "properties": {"risk_level": 0.0},
                },
            ],
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def test_builds_one_authoritative_graph_without_advancing_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime = build_authoritative_autonomous_runtime(
                bootstrap_file=self._bootstrap(root),
                data_dir=root / "data",
                cold_store_dir=root / "cold",
                npc_ids=["npc"],
                tick_duration_ms=250,
            )

            self.assertEqual(runtime.clock.state().tick, 0)
            self.assertEqual(runtime.clock.state().tick_duration_ms, 250)
            self.assertFalse((root / "data" / "world-tick.lock").exists())
            self.assertIs(runtime.scheduler.planner.store, runtime.store)
            self.assertIs(runtime.scheduler.resolver.store, runtime.store)
            self.assertIs(runtime.guarded_mutations.engine, runtime.engine)
            self.assertIs(runtime.cognition.need_scheduler.plans, runtime.scheduler)
            self.assertEqual(runtime.regions.route("r0", "r1"), ["r0", "r1"])
            self.assertIsNotNone(runtime.store.get_entity("npc"))
            self.assertIsNotNone(runtime.store.get_entity("bed"))
            self.assertEqual(runtime.engine.load_world().get("entities"), [])

    def test_reopen_preserves_clock_and_cold_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bootstrap = self._bootstrap(root)
            first = build_authoritative_autonomous_runtime(
                bootstrap_file=bootstrap,
                data_dir=root / "data",
                cold_store_dir=root / "cold",
                npc_ids=["npc"],
            )
            first.clock.advance()
            second = build_authoritative_autonomous_runtime(
                bootstrap_file=bootstrap,
                data_dir=root / "data",
                cold_store_dir=root / "cold",
                npc_ids=["npc"],
            )
            self.assertEqual(second.clock.state().tick, 1)
            self.assertEqual(second.store.get_entity("npc")["region_id"], "r0")

    def test_invalid_topology_fails_closed(self):
        with self.assertRaises(ValueError):
            region_catalog_from_world({
                "regions": [{
                    "id": "r0", "center": {"x": 0, "y": 0},
                    "radius": 10, "neighbors": ["missing"],
                }]
            })


if __name__ == "__main__":
    unittest.main()
