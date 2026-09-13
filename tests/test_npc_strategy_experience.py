from __future__ import annotations

import importlib.util
import sys
import tempfile
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


NpcStrategyExperience = load("npc_strategy_experience_test", RUNTIME / "npc_strategy_experience.py").NpcStrategyExperience
NpcStrategyValue = load("npc_strategy_value_empirical_test", RUNTIME / "npc_strategy_value.py").NpcStrategyValue


class FakeStore:
    def __init__(self):
        self.rows = {
            "npc": {"id": "npc", "region_id": "r0", "properties": {}},
            "a": {"id": "a", "region_id": "r1", "properties": {"risk_level": 0.1}},
            "b": {"id": "b", "region_id": "r1", "properties": {"risk_level": 0.1}},
        }

    def get_entity(self, entity_id):
        return self.rows.get(entity_id)


class FakeRegions:
    def route(self, source, goal):
        return [source, goal]


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()
        self.regions = FakeRegions()


class NpcStrategyExperienceTest(unittest.TestCase):
    def test_online_means_and_outcome_idempotency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = NpcStrategyExperience(Path(tmpdir) / "strategy.json", min_samples=2)
            ctx = {"period": "day", "weather": "clear", "region_id": "r0", "danger_level": 0.2}
            first = exp.observe(outcome_id="o1", npc_id="npc", need="energy", target_entity_id="a", context=ctx,
                                elapsed_ticks=4, preemptions=0, replans=1, observed_risk=0.2)
            self.assertFalse(first["empirical_ready"])
            second = exp.observe(outcome_id="o2", npc_id="npc", need="energy", target_entity_id="a", context=ctx,
                                 elapsed_ticks=8, preemptions=2, replans=1, observed_risk=0.4)
            self.assertTrue(second["empirical_ready"])
            stat = exp.stats("npc", "energy", "a", ctx)
            self.assertEqual(stat["count"], 2)
            self.assertAlmostEqual(stat["mean_elapsed_ticks"], 6.0)
            self.assertAlmostEqual(stat["mean_preemptions"], 1.0)
            self.assertAlmostEqual(stat["mean_replans"], 1.0)
            self.assertAlmostEqual(stat["mean_observed_risk"], 0.3)
            duplicate = exp.observe(outcome_id="o2", npc_id="npc", need="energy", target_entity_id="a", context=ctx,
                                    elapsed_ticks=99, preemptions=99, replans=99, observed_risk=1.0)
            self.assertEqual(duplicate["count"], 2)
            self.assertAlmostEqual(exp.stats("npc", "energy", "a", ctx)["mean_elapsed_ticks"], 6.0)

    def test_strategy_value_switches_from_heuristic_to_empirical_cost(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = {"period": "day", "weather": "clear", "region_id": "r0", "danger_level": 0.0}
            exp = NpcStrategyExperience(Path(tmpdir) / "strategy.json", min_samples=2)
            value = NpcStrategyValue(FakePlanner(), strategy_experience_provider=exp, travel_weight=0.5,
                                     risk_weight=0.0, interruption_weight=0.2, elapsed_ticks_scale=10)
            rankings = [
                {"need": "energy", "target_entity_id": "a", "effective_mean_satisfaction": 0.8, "exploring": False, "context_count": 3},
                {"need": "energy", "target_entity_id": "b", "effective_mean_satisfaction": 0.7, "exploring": False, "context_count": 3},
            ]
            initial = value.evaluate(actor_entity_id="npc", rankings=rankings, context=ctx)
            self.assertTrue(all(row["cost_source"] == "heuristic" for row in initial))

            for idx, ticks in enumerate((10, 10), start=1):
                exp.observe(outcome_id=f"a{idx}", npc_id="npc", need="energy", target_entity_id="a", context=ctx,
                            elapsed_ticks=ticks, preemptions=2, replans=1, observed_risk=0.0)
            for idx, ticks in enumerate((2, 2), start=1):
                exp.observe(outcome_id=f"b{idx}", npc_id="npc", need="energy", target_entity_id="b", context=ctx,
                            elapsed_ticks=ticks, preemptions=0, replans=0, observed_risk=0.0)

            selected, valued = value.choose(actor_entity_id="npc", rankings=rankings, context=ctx)
            self.assertEqual(selected, "b")
            by_id = {row["target_entity_id"]: row for row in valued}
            self.assertEqual(by_id["a"]["cost_source"], "empirical")
            self.assertEqual(by_id["b"]["cost_source"], "empirical")
            self.assertLess(by_id["a"]["expected_value"], by_id["b"]["expected_value"])


if __name__ == "__main__":
    unittest.main()
