from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from npc_need_dynamics import NpcNeedDynamics


class Store:
    def __init__(self) -> None:
        self.entities = {
            "nov": {
                "id": "nov",
                "type": "human",
                "region_id": "r0",
                "position": {"x": 0, "y": 0},
                "properties": {
                    "needs": {
                        "safety": 0.2,
                        "energy": 0.8,
                        "social": 0.5,
                        "curiosity": 0.4,
                    }
                },
            }
        }

    def get_entity(self, entity_id: str):
        row = self.entities.get(entity_id)
        return json.loads(json.dumps(row)) if row is not None else None


def outcome(outcome_id: str, before: float, after: float) -> dict:
    return {
        "outcome_schema": "npc_need_outcome_v1",
        "outcome_id": outcome_id,
        "npc_id": "nov",
        "need": "energy",
        "amount": before - after,
        "before": before,
        "after": after,
        "metadata": {"test": True},
    }


class NeedStateCompaction008LTests(unittest.TestCase):
    def test_legacy_embedded_outcomes_migrate_to_durable_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-state.json"
            legacy = {
                "schema": "npc_need_state_v1",
                "last_tick": 41,
                "npcs": {
                    "nov": {
                        "needs": {
                            "safety": 0.2,
                            "energy": 0.4,
                            "social": 0.5,
                            "curiosity": 0.4,
                        },
                        "last_tick": 41,
                    }
                },
                "applied_outcomes": {
                    "o1": outcome("o1", 0.8, 0.6),
                    "o2": outcome("o2", 0.6, 0.4),
                },
            }
            path.write_text(json.dumps(legacy), encoding="utf-8")
            legacy_bytes = path.stat().st_size

            dynamics = NpcNeedDynamics(path, Store(), npc_ids=["nov"])

            compact = json.loads(path.read_text(encoding="utf-8"))
            journal = path.with_suffix(".outcomes.jsonl")
            rows = [
                json.loads(line)
                for line in journal.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(compact["schema"], "npc_need_state_v2")
            self.assertNotIn("applied_outcomes", compact)
            self.assertEqual(compact["applied_outcome_rows"], 2)
            self.assertEqual([row["outcome_id"] for row in rows], ["o1", "o2"])
            self.assertLess(path.stat().st_size, legacy_bytes)
            self.assertEqual(
                set(dynamics.snapshot()["applied_outcomes"]),
                {"o1", "o2"},
            )

    def test_crash_after_journal_fsync_replays_only_uncheckpointed_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-state.json"
            dynamics = NpcNeedDynamics(path, Store(), npc_ids=["nov"])
            dynamics.advance_tick(1)
            checkpoint_before = path.read_bytes()

            result = dynamics.satisfy(
                "nov",
                "energy",
                0.25,
                outcome_id="crash-gap",
            )
            journal = path.with_suffix(".outcomes.jsonl")
            self.assertTrue(journal.exists())

            # Simulate loss after durable journal append but before compact
            # snapshot checkpoint became visible.
            path.write_bytes(checkpoint_before)

            restarted = NpcNeedDynamics(path, Store(), npc_ids=["nov"])
            self.assertAlmostEqual(
                restarted.get_needs("nov")["energy"],
                result["after"],
                places=9,
            )
            compact = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(compact["applied_outcome_rows"], 1)
            self.assertEqual(
                restarted.satisfy(
                    "nov",
                    "energy",
                    0.25,
                    outcome_id="crash-gap",
                ),
                result,
            )

    def test_restart_idempotency_comes_from_journal_not_snapshot_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-state.json"
            dynamics = NpcNeedDynamics(path, Store(), npc_ids=["nov"])
            dynamics.advance_tick(1)
            first = dynamics.satisfy(
                "nov",
                "energy",
                0.1,
                outcome_id="once",
            )
            journal = path.with_suffix(".outcomes.jsonl")
            size_before = journal.stat().st_size

            restarted = NpcNeedDynamics(path, Store(), npc_ids=["nov"])
            second = restarted.satisfy(
                "nov",
                "energy",
                0.1,
                outcome_id="once",
            )
            self.assertEqual(first, second)
            self.assertEqual(journal.stat().st_size, size_before)
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("applied_outcomes", on_disk)

    def test_hot_snapshot_stays_small_while_outcome_journal_grows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-state.json"
            dynamics = NpcNeedDynamics(path, Store(), npc_ids=["nov"])
            dynamics.advance_tick(1)
            for idx in range(8):
                dynamics.satisfy(
                    "nov",
                    "energy",
                    0.01,
                    outcome_id=f"o-{idx}",
                )
            snapshot_bytes = path.stat().st_size
            journal_bytes = path.with_suffix(".outcomes.jsonl").stat().st_size
            self.assertLess(snapshot_bytes, 4096)
            self.assertGreater(journal_bytes, snapshot_bytes)
            dynamics.advance_tick(2)
            self.assertLess(path.stat().st_size, 4096)

    def test_corrupt_journal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "npc-need-state.json"
            dynamics = NpcNeedDynamics(path, Store(), npc_ids=["nov"])
            dynamics.advance_tick(1)
            path.with_suffix(".outcomes.jsonl").write_text(
                "{not-json}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "corrupt NPC need outcome journal",
            ):
                NpcNeedDynamics(path, Store(), npc_ids=["nov"])

    def test_source_contract_keeps_snapshot_history_out_of_hot_file(self) -> None:
        source = (RUNTIME / "npc_need_dynamics.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("applied_outcome_rows", source)
        self.assertIn("os.fsync(fd)", source)
        self.assertIn("_recover_outcome_tail", source)
        save_block = source.split("def _save(", 1)[1].split(
            "def _read_outcome_journal", 1
        )[0]
        self.assertNotIn('"applied_outcomes"', save_block)

    def test_rollout_backs_up_data_and_only_restarts_single_writer(self) -> None:
        script = (
            ROOT / "deploy" / "apply-compact-need-state-008l.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('backup_one "$STATE"', script)
        self.assertIn('backup_one "$JOURNAL"', script)
        self.assertIn("npc-need-state.json.pre-008l-", script)
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn('restore_one "$STATE"', script)
        self.assertIn('restore_one "$JOURNAL"', script)
        self.assertIn("npc_need_state_v2", script)
        self.assertIn("applied_outcome_rows", script)
        self.assertIn("plans.jsonl.index.sqlite3", script)
        self.assertIn("proposals.jsonl.index.sqlite3", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)


if __name__ == "__main__":
    unittest.main()
