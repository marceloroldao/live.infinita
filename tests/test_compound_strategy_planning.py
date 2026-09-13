from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from packages.spatial import DeterministicIntentPlanner, FileRegionColdStore, Region, RegionCatalog


MODULE_PATH = Path(__file__).resolve().parents[1] / "apps" / "world-runtime" / "npc_compound_strategy.py"
spec = importlib.util.spec_from_file_location("npc_compound_strategy", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
NpcCompoundStrategyCatalog = module.NpcCompoundStrategyCatalog


class CompoundStrategyPlanningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileRegionColdStore(Path(self.tmp.name) / "cold")
        self.store.upsert({"id": "npc", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}})
        self.store.upsert({"id": "shelter", "type": "place", "region_id": "r1", "position": {"x": 500, "y": 0}})
        self.store.upsert({"id": "home", "type": "place", "region_id": "r2", "position": {"x": 1000, "y": 0}})
        self.regions = RegionCatalog([
            Region("r0", (0.0, 0.0), 200.0, neighbors=("r1",)),
            Region("r1", (500.0, 0.0), 200.0, neighbors=("r0", "r2")),
            Region("r2", (1000.0, 0.0), 200.0, neighbors=("r1",)),
        ])
        self.planner = DeterministicIntentPlanner(self.store, self.regions)
        self.catalog = NpcCompoundStrategyCatalog(self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_catalog_exposes_direct_and_via_shelter(self) -> None:
        rows = self.catalog.alternatives(
            actor_entity_id="npc",
            need="energy",
            target_entity_id="home",
            actor_properties={"strategy_shelter_entity_id": "shelter"},
            context={"weather": "storm", "danger_level": 0.8},
        )
        self.assertEqual([row["strategy_kind"] for row in rows], ["direct", "via_shelter"])
        self.assertEqual(rows[1]["intent"]["via_entity_ids"], ["shelter"])

    def test_compound_intent_expands_via_target_then_final_target(self) -> None:
        plan = self.planner.plan({
            "intent": "move_via_entities",
            "actor_entity_id": "npc",
            "via_entity_ids": ["shelter"],
            "target_entity_id": "home",
            "need": "energy",
        })
        self.assertEqual(plan.intent_type, "move_via_entities")
        self.assertEqual(plan.source_region_id, "r0")
        self.assertEqual(plan.goal_region_id, "r2")
        self.assertEqual(plan.region_path, ("r0", "r1", "r2"))
        targets = [step.intent.get("target_entity_id") for step in plan.steps if step.kind in {"compound_goal", "goal"}]
        self.assertEqual(targets, ["shelter", "home"])
        self.assertTrue(all(step.intent.get("intent") in {"move_to_position", "move_to_entity"} for step in plan.steps))

    def test_missing_shelter_falls_back_to_direct_only(self) -> None:
        rows = self.catalog.alternatives(
            actor_entity_id="npc",
            need="energy",
            target_entity_id="home",
            actor_properties={"strategy_shelter_entity_id": "missing"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["strategy_id"], "direct")


if __name__ == "__main__":
    unittest.main()
