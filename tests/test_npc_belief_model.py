import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_belief_model import NpcBeliefModel


class NpcBeliefModelTest(unittest.TestCase):
    def episode(self, episode_id, risk, *, npc_id="nov", region="deep_forest", period="night"):
        return {
            "episode_id": episode_id,
            "npc_id": npc_id,
            "logical_tick": 10,
            "context": {"region_id": region, "period": period, "weather": "clear"},
            "outcome": {"observed_risk": risk},
        }

    def test_reinforcement_and_counterevidence_remain_explicit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model = NpcBeliefModel(Path(tmpdir) / "beliefs.json", prior_strength=2.0)
            first = model.observe_episode(self.episode("e1", 0.8))
            self.assertEqual(first["support_count"], 1)
            self.assertEqual(first["counter_count"], 0)
            self.assertAlmostEqual(first["mean_risk"], 0.8)
            self.assertLess(first["confidence"], 1.0)

            second = model.observe_episode(self.episode("e2", 0.1))
            self.assertEqual(second["support_count"], 1)
            self.assertEqual(second["counter_count"], 1)
            self.assertAlmostEqual(second["mean_risk"], 0.45)
            self.assertGreater(second["confidence"], first["confidence"])

    def test_same_episode_is_idempotent_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "beliefs.json"
            model = NpcBeliefModel(path)
            first = model.observe_episode(self.episode("same", 0.7))
            again = model.observe_episode(self.episode("same", 0.2))
            self.assertEqual(again["count"], 1)
            self.assertAlmostEqual(again["mean_risk"], first["mean_risk"])

            reopened = NpcBeliefModel(path)
            belief = reopened.risk_belief("nov", {"region_id": "deep_forest", "period": "night", "weather": "clear"})
            self.assertIsNotNone(belief)
            self.assertEqual(belief["count"], 1)
            self.assertEqual(belief["last_episode_id"], "same")

    def test_contexts_and_npcs_do_not_leak_into_each_other(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model = NpcBeliefModel(Path(tmpdir) / "beliefs.json")
            model.observe_episode(self.episode("night", 0.9))
            model.observe_episode(self.episode("day", 0.1, period="day"))
            model.observe_episode(self.episode("other", 0.2, npc_id="other"))

            night = model.risk_belief("nov", {"region_id": "deep_forest", "period": "night", "weather": "clear"})
            day = model.risk_belief("nov", {"region_id": "deep_forest", "period": "day", "weather": "clear"})
            other = model.risk_belief("other", {"region_id": "deep_forest", "period": "night", "weather": "clear"})
            self.assertAlmostEqual(night["mean_risk"], 0.9)
            self.assertAlmostEqual(day["mean_risk"], 0.1)
            self.assertAlmostEqual(other["mean_risk"], 0.2)


if __name__ == "__main__":
    unittest.main()
