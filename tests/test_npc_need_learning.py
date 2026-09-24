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


NpcNeedLearning = load("npc_need_learning_test", RUNTIME / "npc_need_learning.py").NpcNeedLearning


class NpcNeedLearningTest(unittest.TestCase):
    def test_online_mean_and_idempotent_outcome(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json", exploration_samples=1)
            first = learning.observe(
                outcome_id="o1", npc_id="npc", need="energy", target_entity_id="bed_a", satisfaction=0.2
            )
            duplicate = learning.observe(
                outcome_id="o1", npc_id="npc", need="energy", target_entity_id="bed_a", satisfaction=0.9
            )
            second = learning.observe(
                outcome_id="o2", npc_id="npc", need="energy", target_entity_id="bed_a", satisfaction=0.6
            )
            self.assertEqual(first, duplicate)
            self.assertEqual(second["count_after"], 2)
            self.assertAlmostEqual(second["mean_satisfaction_after"], 0.4)

    def test_low_sample_targets_are_explored_deterministically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json", exploration_samples=2)
            learning.observe(
                outcome_id="a1", npc_id="npc", need="energy", target_entity_id="bed_a", satisfaction=0.9
            )
            # bed_b has zero samples, so it is explored before exploiting bed_a.
            self.assertEqual(learning.choose_target("npc", "energy", ["bed_a", "bed_b"]), "bed_b")

    def test_after_exploration_best_empirical_target_wins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            learning = NpcNeedLearning(Path(tmpdir) / "learning.json", exploration_samples=1)
            learning.observe(outcome_id="a1", npc_id="npc", need="energy", target_entity_id="bed_a", satisfaction=0.8)
            learning.observe(outcome_id="b1", npc_id="npc", need="energy", target_entity_id="bed_b", satisfaction=0.3)
            self.assertEqual(learning.choose_target("npc", "energy", ["bed_a", "bed_b"]), "bed_a")
            ranked = learning.rank_targets("npc", "energy", ["bed_a", "bed_b"])
            self.assertEqual(ranked[0]["target_entity_id"], "bed_a")
            self.assertGreater(ranked[0]["mean_satisfaction"], ranked[1]["mean_satisfaction"])

    def test_restart_preserves_learning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "learning.json"
            first = NpcNeedLearning(path, exploration_samples=1)
            first.observe(outcome_id="a1", npc_id="npc", need="social", target_entity_id="nov", satisfaction=0.7)
            reopened = NpcNeedLearning(path, exploration_samples=1)
            stat = reopened.stats("npc", "social", "nov")
            self.assertIsNotNone(stat)
            self.assertEqual(stat["count"], 1)
            self.assertAlmostEqual(stat["mean_satisfaction"], 0.7)


if __name__ == "__main__":
    unittest.main()
