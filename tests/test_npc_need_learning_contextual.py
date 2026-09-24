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


NpcNeedLearning = load("npc_need_learning_contextual_test", RUNTIME / "npc_need_learning.py").NpcNeedLearning


DAY = {"period": "day", "weather": "clear", "danger_level": 0.1, "region_id": "village"}
NIGHT = {"period": "night", "weather": "clear", "danger_level": 0.1, "region_id": "village"}
STORM = {"period": "night", "weather": "storm", "danger_level": 0.8, "region_id": "village"}


class NpcNeedLearningContextualTest(unittest.TestCase):
    def observe(self, learning, idx, target, reward, context):
        return learning.observe(
            outcome_id=f"outcome_{idx}",
            npc_id="npc",
            need="energy",
            target_entity_id=target,
            satisfaction=reward,
            plan_id=f"plan_{idx}",
            context=context,
        )

    def test_same_target_keeps_global_and_contextual_means(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json", exploration_samples=0, contextual_min_samples=1)
            self.observe(learning, 1, "a", 0.8, DAY)
            self.observe(learning, 2, "a", 0.2, NIGHT)

            global_stat = learning.stats("npc", "energy", "a")
            day_stat = learning.contextual_stats("npc", "energy", "a", DAY)
            night_stat = learning.contextual_stats("npc", "energy", "a", NIGHT)

            self.assertAlmostEqual(global_stat["mean_satisfaction"], 0.5)
            self.assertAlmostEqual(day_stat["mean_satisfaction"], 0.8)
            self.assertAlmostEqual(night_stat["mean_satisfaction"], 0.2)

    def test_context_can_reverse_global_target_preference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json", exploration_samples=0, contextual_min_samples=2)
            # Globally A is strong and B is weak.
            self.observe(learning, 1, "a", 0.9, DAY)
            self.observe(learning, 2, "a", 0.9, DAY)
            self.observe(learning, 3, "b", 0.3, DAY)
            self.observe(learning, 4, "b", 0.3, DAY)
            # At night, enough contextual evidence shows the opposite.
            self.observe(learning, 5, "a", 0.1, NIGHT)
            self.observe(learning, 6, "a", 0.1, NIGHT)
            self.observe(learning, 7, "b", 0.8, NIGHT)
            self.observe(learning, 8, "b", 0.8, NIGHT)

            self.assertEqual(learning.choose_target("npc", "energy", ["a", "b"], context=DAY), "a")
            self.assertEqual(learning.choose_target("npc", "energy", ["a", "b"], context=NIGHT), "b")

    def test_sparse_context_falls_back_to_global_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json", exploration_samples=0, contextual_min_samples=2)
            self.observe(learning, 1, "a", 0.8, DAY)
            self.observe(learning, 2, "a", 0.8, DAY)
            self.observe(learning, 3, "b", 0.4, DAY)
            self.observe(learning, 4, "b", 0.4, DAY)
            # One storm sample is deliberately insufficient for contextual exploitation.
            self.observe(learning, 5, "b", 1.0, STORM)

            ranked = learning.rank_targets("npc", "energy", ["a", "b"], context=STORM)
            self.assertEqual(ranked[0]["target_entity_id"], "a")
            self.assertEqual(ranked[0]["evidence_source"], "global_fallback")

    def test_context_is_canonicalized_and_danger_is_bucketed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json")
            a = learning.context_key({"period": " Night ", "weather": "Storm", "danger_level": 0.91, "region_id": "r1"})
            b = learning.context_key({"region_id": "r1", "danger_level": 0.70, "weather": "storm", "period": "night"})
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
