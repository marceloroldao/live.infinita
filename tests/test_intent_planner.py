from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from packages.spatial import DeterministicIntentPlanner, FileRegionColdStore, IntentPlanError, Region, RegionCatalog


class IntentPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileRegionColdStore(Path(self.tmp.name) / "cold")
        self.store.upsert({"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}})
        self.store.upsert({"id": "bridge", "type": "bridge", "region_id": "r2", "position": {"x": 1000, "y": 25}})
        self.regions = RegionCatalog([
            Region("r0", (0.0, 0.0), 200.0, neighbors=("r1",)),
            Region("r1", (500.0, 0.0), 200.0, neighbors=("r0", "r2")),
            Region("r2", (1000.0, 0.0), 200.0, neighbors=("r1",)),
        ])
        self.planner = DeterministicIntentPlanner(self.store, self.regions)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_move_to_entity_expands_region_route_then_goal(self) -> None:
        plan = self.planner.plan({
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
        })
        self.assertEqual(plan.region_path, ("r0", "r1", "r2"))
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0].kind, "region_waypoint")
        self.assertEqual(plan.steps[0].expected_region_id, "r0")
        self.assertEqual(plan.steps[0].intent["region_id"], "r1")
        self.assertEqual(plan.steps[1].expected_region_id, "r1")
        self.assertEqual(plan.steps[1].intent["region_id"], "r2")
        self.assertEqual(plan.steps[2].kind, "goal")
        self.assertEqual(plan.steps[2].expected_region_id, "r2")
        self.assertEqual(plan.steps[2].intent["target_entity_id"], "bridge")

    def test_non_movement_intent_remains_one_semantic_step(self) -> None:
        plan = self.planner.plan({
            "intent": "establish_relation",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
            "relation": "sees",
        })
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].kind, "semantic")

    def test_step_revalidation_fails_when_actor_left_expected_region(self) -> None:
        plan = self.planner.plan({
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "bridge",
        })
        nov = self.store.get_entity("nov")
        assert nov is not None
        nov["region_id"] = "r2"
        nov["position"] = {"x": 900, "y": 0}
        self.store.upsert(nov)
        with self.assertRaises(IntentPlanError):
            self.planner.revalidate_step(plan, 0)

    def test_disconnected_regions_fail_closed(self) -> None:
        isolated = RegionCatalog([
            Region("r0", (0.0, 0.0), 100.0),
            Region("r2", (1000.0, 0.0), 100.0),
        ])
        planner = DeterministicIntentPlanner(self.store, isolated)
        with self.assertRaises(IntentPlanError):
            planner.plan({
                "intent": "move_to_entity",
                "actor_entity_id": "nov",
                "target_entity_id": "bridge",
            })


if __name__ == "__main__":
    unittest.main()
