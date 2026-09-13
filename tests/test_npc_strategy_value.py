from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

NpcStrategyValue = load("npc_strategy_value_test", RUNTIME / "npc_strategy_value.py").NpcStrategyValue


class FakeStore:
    def __init__(self):
        self.rows = {
            "npc": {"id": "npc", "region_id": "r0"},
            "near": {"id": "near", "region_id": "r1", "properties": {"risk_level": 0.0}},
            "far": {"id": "far", "region_id": "r4", "properties": {"risk_level": 0.7}},
        }

    def get_entity(self, entity_id):
        row = self.rows.get(entity_id)
        return dict(row) if row else None


class FakeRegions:
    ROUTES = {
        ("r0", "r1"): ["r0", "r1"],
        ("r0", "r4"): ["r0", "r1", "r2", "r3", "r4"],
    }

    def route(self, source, goal):
        return list(self.ROUTES.get((source, goal), []))


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()
        self.regions = FakeRegions()


class NpcStrategyValueTest(unittest.TestCase):
    def test_safer_nearer_target_can_beat_higher_predicted_satisfaction(self):
        value = NpcStrategyValue(FakePlanner(), travel_weight=0.20, risk_weight=0.50, route_hops_scale=4)
        rankings = [
            {"target_entity_id": "near", "effective_mean_satisfaction": 0.65, "exploring": False, "context_count": 4},
            {"target_entity_id": "far", "effective_mean_satisfaction": 0.90, "exploring": False, "context_count": 4},
        ]
        selected, valued = value.choose(actor_entity_id="npc", rankings=rankings, context={"danger_level": 0.0})
        self.assertEqual(selected, "near")
        self.assertGreater(valued[0]["expected_value"], valued[1]["expected_value"])
        self.assertEqual(valued[0]["route_hops"], 1)
        self.assertEqual(valued[1]["route_hops"], 4)

    def test_exploration_group_stays_ahead_of_known_targets(self):
        value = NpcStrategyValue(FakePlanner(), travel_weight=0.20, risk_weight=0.50, route_hops_scale=4)
        rankings = [
            {"target_entity_id": "near", "effective_mean_satisfaction": 0.95, "exploring": False, "context_count": 5},
            {"target_entity_id": "far", "effective_mean_satisfaction": 0.10, "exploring": True, "context_count": 0},
        ]
        selected, valued = value.choose(actor_entity_id="npc", rankings=rankings, context={"danger_level": 0.0})
        self.assertEqual(selected, "far")
        self.assertTrue(valued[0]["exploring"])

    def test_world_danger_penalizes_all_targets_deterministically(self):
        value = NpcStrategyValue(FakePlanner(), travel_weight=0.0, risk_weight=0.5)
        rankings = [{"target_entity_id": "near", "effective_mean_satisfaction": 0.8, "exploring": False, "context_count": 3}]
        _, safe = value.choose(actor_entity_id="npc", rankings=rankings, context={"danger_level": 0.0})
        _, danger = value.choose(actor_entity_id="npc", rankings=rankings, context={"danger_level": 0.8})
        self.assertGreater(safe[0]["expected_value"], danger[0]["expected_value"])
        self.assertAlmostEqual(danger[0]["risk"], 0.8)


if __name__ == "__main__":
    unittest.main()
