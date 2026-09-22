import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from npc_episodic_memory import NpcEpisodicMemory


class NpcEpisodicMemoryTest(unittest.TestCase):
    def test_remember_is_idempotent_and_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "episodes.jsonl"
            memory = NpcEpisodicMemory(path)
            first = memory.remember(
                episode_id="e1",
                npc_id="nov",
                logical_tick=12,
                need="safety",
                target_entity_id="shelter",
                strategy_id="direct",
                context={"period": "night", "weather": "clear", "region_id": "clearing", "danger_level": 0.35},
                satisfaction=0.4,
                elapsed_ticks=2,
                observed_risk=0.35,
            )
            duplicate = memory.remember(
                episode_id="e1",
                npc_id="nov",
                logical_tick=99,
                need="curiosity",
                target_entity_id="tree",
                strategy_id="direct",
                context={"period": "day"},
                satisfaction=0.0,
                elapsed_ticks=9,
            )
            self.assertEqual(first, duplicate)
            self.assertEqual(len(memory.history()), 1)

            reopened = NpcEpisodicMemory(path)
            self.assertEqual(reopened.history(), [first])

    def test_recall_prefers_semantic_and_context_match_then_recency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = NpcEpisodicMemory(Path(tmpdir) / "episodes.jsonl")
            base = dict(
                npc_id="nov",
                need="safety",
                target_entity_id="shelter",
                strategy_id="direct",
                satisfaction=0.3,
                elapsed_ticks=2,
            )
            memory.remember(
                episode_id="night-old",
                logical_tick=10,
                context={"period": "night", "weather": "clear", "region_id": "clearing", "danger_level": 0.35},
                **base,
            )
            memory.remember(
                episode_id="day-newer",
                logical_tick=20,
                context={"period": "day", "weather": "clear", "region_id": "clearing", "danger_level": 0.05},
                **base,
            )
            memory.remember(
                episode_id="night-new",
                logical_tick=30,
                context={"period": "night", "weather": "clear", "region_id": "clearing", "danger_level": 0.35},
                **base,
            )

            recalled = memory.recall(
                "nov",
                need="safety",
                target_entity_id="shelter",
                strategy_id="direct",
                context={"period": "night", "weather": "clear", "region_id": "clearing", "danger_level": 0.35},
                limit=3,
            )
            self.assertEqual([row["episode_id"] for row in recalled], ["night-new", "night-old", "day-newer"])

    def test_recall_is_scoped_by_npc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = NpcEpisodicMemory(Path(tmpdir) / "episodes.jsonl")
            for npc_id in ("nov", "other"):
                memory.remember(
                    episode_id=f"e-{npc_id}",
                    npc_id=npc_id,
                    logical_tick=1,
                    need="energy",
                    target_entity_id="bed",
                    strategy_id="direct",
                    context={"period": "day"},
                    satisfaction=0.2,
                    elapsed_ticks=1,
                )
            self.assertEqual([row["episode_id"] for row in memory.recall("nov")], ["e-nov"])


if __name__ == "__main__":
    unittest.main()
