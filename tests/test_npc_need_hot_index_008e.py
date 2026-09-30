from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from hot_ledger_compactor import compact_need_scheduler
from npc_need_scheduler import NpcNeedScheduler


class FakeProposalLedger:
    pass


class FakeStore:
    def get_entity(self, entity_id):
        return None


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()


class FakePlanScheduler:
    def __init__(self):
        self.planner = FakePlanner()


class NpcNeedHotIndex008ETests(unittest.TestCase):
    def test_compaction_preserves_latest_audit_and_both_scheduled_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-scheduler.jsonl"
            rows = [
                {
                    "npc_id": "nov",
                    "original_need": "curiosity",
                    "need": "safety",
                    "status": "scheduled",
                    "tick": 10,
                },
                {
                    "npc_id": "nov",
                    "original_need": "curiosity",
                    "need": "curiosity",
                    "status": "no_target",
                    "tick": 11,
                },
                {
                    "npc_id": "nov",
                    "original_need": "energy",
                    "need": "energy",
                    "status": "scheduled",
                    "tick": 12,
                },
                {
                    "npc_id": "nov",
                    "original_need": "energy",
                    "need": "energy",
                    "status": "cooldown",
                    "tick": 13,
                },
                {
                    "npc_id": "nov",
                    "original_need": "curiosity",
                    "need": "social",
                    "status": "scheduled",
                    "tick": 14,
                },
                {
                    "npc_id": "nov",
                    "original_need": "curiosity",
                    "need": "curiosity",
                    "status": "no_target",
                    "tick": 15,
                },
            ]
            path.write_text(
                "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
                encoding="utf-8",
            )

            result = compact_need_scheduler(path)
            self.assertEqual(result["original_rows"], 6)
            self.assertEqual(result["latest_audit_keys"], 2)
            self.assertEqual(result["latest_scheduled_original_keys"], 2)
            self.assertEqual(result["latest_scheduled_actual_keys"], 3)
            self.assertEqual(result["latest_rows"], 5)
            self.assertFalse(result["history_deleted"])

            scheduler = NpcNeedScheduler(
                path,
                FakeProposalLedger(),
                FakePlanScheduler(),
                npc_ids=["nov"],
                threshold=0.7,
                cooldown_ticks=20,
            )
            self.assertEqual(scheduler._last_tick("nov", "safety"), 10)
            self.assertEqual(scheduler._last_tick("nov", "energy"), 12)
            self.assertEqual(scheduler._last_tick("nov", "social"), 14)

            curiosity = scheduler._last_scheduled_original("nov", "curiosity")
            energy = scheduler._last_scheduled_original("nov", "energy")
            self.assertEqual(curiosity["tick"], 14)
            self.assertEqual(curiosity["need"], "social")
            self.assertEqual(energy["tick"], 12)

            scheduler._ensure_index()
            self.assertEqual(
                scheduler._latest_audit[("nov", "curiosity")]["tick"],
                15,
            )
            self.assertEqual(
                scheduler._latest_audit[("nov", "energy")]["tick"],
                13,
            )
            self.assertEqual(scheduler.history(), rows)

    def test_post_compaction_history_skips_synthetic_snapshot_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-scheduler.jsonl"
            rows = [
                {
                    "npc_id": "nov",
                    "need": "energy",
                    "status": "scheduled",
                    "tick": 1,
                },
                {
                    "npc_id": "nov",
                    "need": "energy",
                    "status": "cooldown",
                    "tick": 2,
                },
            ]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            compact_need_scheduler(path)
            appended = {
                "npc_id": "nov",
                "need": "energy",
                "status": "scheduled",
                "tick": 30,
            }
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(appended) + "\n")

            scheduler = NpcNeedScheduler(
                path,
                FakeProposalLedger(),
                FakePlanScheduler(),
                npc_ids=["nov"],
            )
            self.assertEqual(scheduler.history(), rows + [appended])
            self.assertEqual(scheduler._last_tick("nov", "energy"), 30)

    def test_compaction_is_idempotent_via_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-scheduler.jsonl"
            path.write_text(
                json.dumps({
                    "npc_id": "nov",
                    "need": "energy",
                    "status": "scheduled",
                    "tick": 5,
                }) + "\n",
                encoding="utf-8",
            )
            first = compact_need_scheduler(path)
            second = compact_need_scheduler(path)
            self.assertFalse(first.get("already_compacted", False))
            self.assertTrue(second["already_compacted"])
            self.assertEqual(second["archive"], first["archive"])

    def test_rollout_restarts_only_single_writer_and_requires_tick_recovery(self) -> None:
        script = (ROOT / "deploy" / "apply-need-hot-index-008e.sh").read_text(encoding="utf-8")
        self.assertIn("live-infinita-autonomous-world.service", script)
        self.assertIn("--needs", script)
        self.assertIn('assert value["history_deleted"] is False', script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("single writer não retomou avanço lógico", script)
        self.assertIn("LIVE_INFINITA_WORLD_BUILDER=1", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)
        self.assertNotIn('rm -f "$DATA/npc-need-scheduler.jsonl"', script)


if __name__ == "__main__":
    unittest.main()
