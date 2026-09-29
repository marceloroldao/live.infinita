from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps/world-runtime/nov_local_memory_sync.py"
SPEC = importlib.util.spec_from_file_location("nov_local_memory_sync", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_episode(index: int) -> dict:
    plan = f"plan_{index}"
    return {
        "episode_schema": "npc_episode_v1",
        "episode_id": "plan:" + plan,
        "npc_id": "nov",
        "logical_tick": index + 10,
        "need": "curiosity",
        "target_entity_id": "ancient_tree",
        "strategy_id": "via_shelter:shelter_marker",
        "context": {"region_id": "clearing", "weather": "clear", "period": "day", "danger_level": 0.1},
        "outcome": {"satisfaction": 0.3, "observed_risk": 0.1, "elapsed_ticks": 3, "preemptions": 0, "replans": 0},
        "source": {"kind": "need_outcome", "plan_id": plan, "proposal_id": f"proposal_{index}", "plan_revision": 0},
    }


def receipt_for(value: dict, *, stored: bool = True) -> dict:
    return {
        "schema": value["schema"],
        "ack": True,
        "stored": stored,
        "record_key": value["record_key"],
        "content_sha256": value["content_sha256"],
        "episode_id": value["source"]["episode_id"],
        "world_id": value["source"]["world_id"],
        "evidence_id": "local:evidence:" + value["record_key"][:20],
        "persistence": {"backend": "sqlite", "state_id": "snapshot:" + value["record_key"], "sha256": "1" * 64},
        "world_mutated": False,
        "selection_authority": False,
    }


class LocalMemorySyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nov-local-memory-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.world = self.root / "world.json"
        self.ledger = self.root / "npc-episodes.jsonl"
        self.checkpoint = self.root / "memoria-local/checkpoint.json"
        self.world.write_text(json.dumps({"world_id": "nov-live-autonomous-001"}), encoding="utf-8")
        self.rows = [sample_episode(1), sample_episode(2), sample_episode(3)]
        self.write_rows()

    def write_rows(self):
        self.ledger.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in self.rows))

    def send(self, value):
        return receipt_for(value)

    def run_sync(self, *, send=None, max_episodes=2):
        return MODULE.sync_once(self.ledger, self.world, self.checkpoint, send=send or self.send, max_episodes=max_episodes)

    def test_bounded_progress_and_durable_ack(self):
        before = self.ledger.read_bytes()
        first = self.run_sync()
        cp = json.loads(self.checkpoint.read_text())
        self.assertEqual(first["acked"], 2)
        self.assertEqual(cp["confirmed_episodes"], 2)
        self.assertTrue(cp["last_acked_record_key"])
        self.assertEqual(self.checkpoint.stat().st_mode & 0o777, 0o600)
        second = self.run_sync()
        self.assertEqual(second["acked"], 1)
        self.assertEqual(self.run_sync()["acked"], 0)
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertFalse(first["world_mutated"])
        self.assertFalse(first["central_sync"])

    def test_transport_retry_does_not_move_cursor_without_ack(self):
        def fail(_):
            raise MODULE.LocalMemorySyncError("local_server_http_502")
        with self.assertRaisesRegex(MODULE.LocalMemorySyncError, "local_server_http_502"):
            self.run_sync(send=fail)
        self.assertFalse(self.checkpoint.exists())
        self.assertEqual(self.run_sync(max_episodes=1)["acked"], 1)

    def test_bad_receipts_never_commit_checkpoint(self):
        original = self.send(self.envelope())
        failures = [
            {**original, "ack": False},
            {**original, "record_key": "0" * 64},
            {**original, "content_sha256": "0" * 64},
            {**original, "world_id": "another-world"},
            {**original, "persistence": {}},
            {**original, "selection_authority": True},
            {**original, "world_mutated": True},
        ]
        for bad in failures:
            with self.subTest(bad=bad):
                with self.assertRaises(MODULE.LocalMemorySyncError):
                    self.run_sync(send=lambda _: bad, max_episodes=1)
                self.assertFalse(self.checkpoint.exists())

    def envelope(self):
        from packages.observability.nov_episode_sync import observation_envelope
        return observation_envelope(self.rows[0], world_id="nov-live-autonomous-001")

    def test_duplicate_receipt_is_safe_and_not_counted_new(self):
        result = self.run_sync(send=lambda envelope: receipt_for(envelope, stored=False), max_episodes=1)
        self.assertEqual(result["acked"], 1)
        self.assertEqual(result["stored"], 0)
        self.assertTrue(self.checkpoint.exists())

    def test_ledger_rewrite_and_rotation_block_progress(self):
        self.run_sync(max_episodes=1)
        self.rows[0]["outcome"]["satisfaction"] = 0.95
        self.write_rows()
        with self.assertRaisesRegex(MODULE.LocalMemorySyncError, "ledger_prefix_rewritten|last_acked_line_rewritten"):
            self.run_sync()
        self.rows[0]["outcome"]["satisfaction"] = 0.3
        self.write_rows()
        self.ledger.replace(self.root / "rotated.jsonl")
        self.write_rows()
        with self.assertRaisesRegex(MODULE.LocalMemorySyncError, "ledger_inode_changed"):
            self.run_sync()

    def test_partial_line_is_not_acknowledged(self):
        self.run_sync(max_episodes=2)
        self.ledger.write_bytes(self.ledger.read_bytes().removesuffix(b"\n"))
        # Existing ledger record is truncated after an earlier ACK, fail closed.
        with self.assertRaisesRegex(MODULE.LocalMemorySyncError, "last_acked_line_rewritten|ledger_prefix_rewritten|ledger_truncated"):
            self.run_sync()

    def test_partial_new_tail_waits_without_advancing(self):
        self.run_sync(max_episodes=3)
        before = json.loads(self.checkpoint.read_text())["cursor"]
        with self.ledger.open("ab") as file:
            file.write(json.dumps(sample_episode(4)).encode())
        self.assertEqual(self.run_sync()["acked"], 0)
        self.assertEqual(json.loads(self.checkpoint.read_text())["cursor"], before)
        with self.ledger.open("ab") as file:
            file.write(b"\n")
        self.assertEqual(self.run_sync()["acked"], 1)

    def test_restart_resume_preserves_provenance_and_world_identity(self):
        self.run_sync(max_episodes=1)
        self.world.write_text(json.dumps({"world_id": "different-world"}), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.LocalMemorySyncError, "world_identity_changed"):
            self.run_sync()
        self.assertEqual(json.loads(self.checkpoint.read_text())["confirmed_episodes"], 1)

    def test_no_source_text_or_central_transport_logic(self):
        code = MODULE_PATH.read_text()
        self.assertIn("127.0.0.1:8788", code)
        self.assertNotIn("memoria.ia.server", code)
        self.assertNotIn("world_tick", code)
        self.assertNotIn("commit_action", code)
        self.assertNotIn("main_spatial", code)


if __name__ == "__main__":
    unittest.main()
