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


class FakeStore:
    def get_entity(self, entity_id: str):
        return None


class FakePlanner:
    def __init__(self) -> None:
        self.store = FakeStore()


class FakePlans:
    def __init__(self) -> None:
        self.planner = FakePlanner()


class FakeProposals:
    pass


class NeedHotIndex008ETests(unittest.TestCase):
    def _rows(self) -> list[dict]:
        return [
            {
                "npc_id": "nov",
                "original_need": "safety",
                "need": "safety",
                "status": "scheduled",
                "tick": 10,
                "proposal_id": "p1",
            },
            {
                "npc_id": "nov",
                "original_need": "social",
                "need": "social",
                "status": "no_target",
                "tick": 11,
            },
            {
                "npc_id": "nov",
                "original_need": "energy",
                "need": "energy",
                "status": "scheduled",
                "tick": 12,
                "proposal_id": "p2",
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
                "original_need": "safety",
                "need": "safety",
                "status": "no_target",
                "tick": 20,
            },
        ]

    def _write(self, path: Path) -> list[dict]:
        rows = self._rows()
        path.write_text(
            "".join(
                json.dumps(row, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        return rows

    def test_compaction_preserves_latest_audit_and_last_scheduled_cooldowns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-needs.jsonl"
            original = self._write(path)

            result = compact_need_scheduler(path)

            self.assertEqual(result["kind"], "npc_need_scheduler")
            self.assertEqual(result["original_rows"], 5)
            self.assertEqual(result["latest_audit_keys"], 3)
            self.assertEqual(result["latest_scheduled_original_keys"], 2)
            self.assertEqual(result["latest_scheduled_actual_keys"], 2)
            self.assertEqual(result["latest_rows"], 5)
            self.assertFalse(result["history_deleted"])
            self.assertTrue((path.parent / result["archive"]).is_file())

            scheduler = NpcNeedScheduler(
                path,
                FakeProposals(),
                FakePlans(),
                npc_ids=["nov"],
            )
            self.assertEqual(scheduler._last_tick("nov", "safety"), 10)
            self.assertEqual(scheduler._last_tick("nov", "energy"), 12)
            self.assertIsNone(scheduler._last_tick("nov", "social"))
            self.assertEqual(
                scheduler._last_scheduled_original("nov", "safety")["tick"],
                10,
            )
            self.assertEqual(
                scheduler._last_scheduled_original("nov", "energy")["tick"],
                12,
            )
            scheduler._ensure_index()
            self.assertEqual(
                scheduler._latest_audit[("nov", "safety")]["status"],
                "no_target",
            )
            self.assertEqual(
                scheduler._latest_audit[("nov", "energy")]["status"],
                "cooldown",
            )
            self.assertEqual(scheduler.history(), original)

    def test_post_compaction_append_updates_hot_index_and_history_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-needs.jsonl"
            original = self._write(path)
            result = compact_need_scheduler(path)
            scheduler = NpcNeedScheduler(
                path,
                FakeProposals(),
                FakePlans(),
                npc_ids=["nov"],
            )
            scheduler._ensure_index()
            appended = scheduler._append({
                "npc_id": "nov",
                "original_need": "social",
                "need": "social",
                "status": "scheduled",
                "tick": 30,
                "proposal_id": "p3",
            })
            self.assertEqual(appended["status"], "scheduled")
            self.assertEqual(scheduler._last_tick("nov", "social"), 30)
            self.assertEqual(
                scheduler._last_scheduled_original("nov", "social")["tick"],
                30,
            )
            self.assertEqual(scheduler.history(), original + [appended])
            self.assertEqual(
                len(path.read_text(encoding="utf-8").splitlines()),
                int(result["latest_rows"]) + 1,
            )

    def test_compaction_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-needs.jsonl"
            self._write(path)
            first = compact_need_scheduler(path)
            second = compact_need_scheduler(path)
            self.assertEqual(first["source_sha256"], second["source_sha256"])
            self.assertTrue(second["already_compacted"])

    def test_source_contract_does_not_change_need_policy(self) -> None:
        source = (RUNTIME / "npc_need_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_PRIORITIES", source)
        self.assertIn("self.threshold", source)
        self.assertIn("self.cooldown_ticks", source)
        self.assertIn("npc need compaction manifest invalid", source)
        self.assertNotIn("compact_need_scheduler(", source)

    def test_rollout_is_single_writer_only_and_requires_tick_recovery(self) -> None:
        script = (ROOT / "deploy" / "apply-need-hot-index-008e.sh").read_text(encoding="utf-8")
        self.assertIn("live-infinita-autonomous-world.service", script)
        self.assertIn("--needs", script)
        self.assertIn('assert value["history_deleted"] is False', script)
        self.assertIn("latest_scheduled_original_keys", script)
        self.assertIn("latest_scheduled_actual_keys", script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("single writer não retomou avanço", script)
        self.assertIn("LIVE_INFINITA_WORLD_BUILDER=", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)
        self.assertNotIn('rm -f "$DATA/npc-need-scheduler.jsonl"', script)


if __name__ == "__main__":
    unittest.main()
