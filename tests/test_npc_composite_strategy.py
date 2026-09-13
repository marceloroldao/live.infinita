import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "world-runtime"))
sys.path.insert(0, str(ROOT))

from npc_composite_strategy import NpcCompositeStrategy
from packages.spatial import FileRegionColdStore, Region, RegionCatalog


class NpcCompositeStrategyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = FileRegionColdStore(root / "cold")
        self.regions = RegionCatalog([
            Region("r0", (0.0, 0.0), 5.0, neighbors=("r1",)),
            Region("r1", (10.0, 0.0), 5.0, neighbors=("r0", "r2")),
            Region("r2", (20.0, 0.0), 5.0, neighbors=("r1",)),
        ])
        for entity in [
            {"id": "npc", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}, "properties": {}},
            {"id": "goal", "type": "place", "region_id": "r2", "position": {"x": 20, "y": 0}, "properties": {"risk_level": 0.8}},
            {"id": "shelter", "type": "place", "region_id": "r1", "position": {"x": 10, "y": 0}, "properties": {"risk_level": 0.05}},
        ]:
            self.store.upsert(entity)

        class Planner:
            pass
        planner = Planner()
        planner.store = self.store
        planner.regions = self.regions
        self.strategy = NpcCompositeStrategy(planner, wait_penalty_per_tick=0.03)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generates_direct_via_shelter_and_wait(self):
        rows = self.strategy.candidates(
            actor_entity_id="npc",
            target_entity_id="goal",
            predicted_satisfaction=0.8,
            context={"danger_level": 0.6},
            shelter_entity_ids=["shelter"],
            wait_ticks=4,
        )
        ids = {row["strategy_id"] for row in rows}
        self.assertEqual(ids, {"direct", "via_shelter:shelter", "wait_then_direct"})
        via = next(row for row in rows if row["strategy_id"].startswith("via_shelter"))
        self.assertEqual([phase["kind"] for phase in via["phases"]], ["move_to_entity", "move_to_entity"])

    def test_wait_has_explicit_temporal_penalty(self):
        rows = self.strategy.candidates(
            actor_entity_id="npc",
            target_entity_id="goal",
            predicted_satisfaction=0.8,
            context={"danger_level": 0.0},
            wait_ticks=5,
        )
        ranked = self.strategy.rank(rows, travel_weight=0.0, risk_weight=0.0)
        direct = next(row for row in ranked if row["strategy_id"] == "direct")
        wait = next(row for row in ranked if row["strategy_id"] == "wait_then_direct")
        self.assertEqual(wait["wait_penalty"], 0.15)
        self.assertGreater(direct["expected_value"], wait["expected_value"])

    def test_via_shelter_can_win_when_risk_penalty_dominates(self):
        rows = self.strategy.candidates(
            actor_entity_id="npc",
            target_entity_id="goal",
            predicted_satisfaction=0.8,
            context={"danger_level": 0.9},
            shelter_entity_ids=["shelter"],
            wait_ticks=0,
        )
        for row in rows:
            if row["strategy_id"] == "via_shelter:shelter":
                row["estimated_risk"] = 0.1
        chosen, ranked = self.strategy.choose(rows, travel_weight=0.05, risk_weight=0.8)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["strategy_id"], "via_shelter:shelter")
        self.assertEqual(ranked[0]["strategy_id"], "via_shelter:shelter")

    def test_missing_entities_fail_closed_to_no_candidates(self):
        self.assertEqual(
            self.strategy.candidates(
                actor_entity_id="missing",
                target_entity_id="goal",
                predicted_satisfaction=1.0,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
