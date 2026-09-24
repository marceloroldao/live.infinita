import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_audited_reordering_need_scheduler import NpcAuditedReorderingNeedScheduler


class DummyScheduler(NpcAuditedReorderingNeedScheduler):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)


class NpcGoalReconsiderationAuditTest(unittest.TestCase):
    def test_links_first_reconsideration_to_latest_pending_reorder_only_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = DummyScheduler(Path(tmpdir) / "history.jsonl")
            scheduler._append({
                "npc_id": "nov",
                "need": "safety",
                "original_need": "curiosity",
                "horizon_reordered": True,
                "status": "scheduled",
                "tick": 10,
                "proposal_id": "proposal_reorder_1",
            })
            reconsidered = scheduler._append({
                "npc_id": "nov",
                "need": "curiosity",
                "original_need": "curiosity",
                "horizon_reordered": False,
                "status": "scheduled",
                "tick": 20,
                "proposal_id": "proposal_curiosity_1",
            })
            self.assertEqual(reconsidered["reconsidered_from_proposal_id"], "proposal_reorder_1")
            self.assertEqual(reconsidered["reconsidered_from_tick"], 10)
            self.assertEqual(reconsidered["reconsidered_after_need"], "safety")

            second_cycle = scheduler._append({
                "npc_id": "nov",
                "need": "curiosity",
                "original_need": "curiosity",
                "horizon_reordered": False,
                "status": "scheduled",
                "tick": 30,
                "proposal_id": "proposal_curiosity_2",
            })
            self.assertNotIn("reconsidered_from_proposal_id", second_cycle)

    def test_other_need_does_not_consume_pending_reconsideration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = DummyScheduler(Path(tmpdir) / "history.jsonl")
            scheduler._append({
                "npc_id": "nov", "need": "safety", "original_need": "curiosity",
                "horizon_reordered": True, "status": "scheduled", "tick": 10,
                "proposal_id": "proposal_reorder_1",
            })
            unrelated = scheduler._append({
                "npc_id": "nov", "need": "energy", "original_need": "energy",
                "horizon_reordered": False, "status": "scheduled", "tick": 15,
                "proposal_id": "proposal_energy_1",
            })
            self.assertNotIn("reconsidered_from_proposal_id", unrelated)

            curiosity = scheduler._append({
                "npc_id": "nov", "need": "curiosity", "original_need": "curiosity",
                "horizon_reordered": False, "status": "scheduled", "tick": 20,
                "proposal_id": "proposal_curiosity_1",
            })
            self.assertEqual(curiosity["reconsidered_from_proposal_id"], "proposal_reorder_1")


if __name__ == "__main__":
    unittest.main()
