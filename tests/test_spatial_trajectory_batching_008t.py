from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "apps" / "world-runtime" / "nov_spatial_memory_sync.py"
spec = importlib.util.spec_from_file_location("nov_spatial_memory_sync_008t", SYNC_PATH)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SpatialTrajectoryBatching008TTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.world = self.root / "world.json"
        self.delta = self.root / "deltas.jsonl"
        self.checkpoint = self.root / "checkpoint.json"
        self.world.write_text(json.dumps({"world_id": "world-test"}), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def row(sequence: int, x: float, y: float) -> dict:
        return {
            "event_id": f"evt_{sequence}",
            "sequence": sequence,
            "result_hash": ("%064x" % sequence)[-64:],
            "operations": [{
                "op": "move",
                "entity_id": "nov",
                "position": {"x": x, "y": y},
                "region_id": "forest",
            }],
        }

    def write_rows(self, count: int) -> None:
        self.delta.write_text(
            "".join(
                json.dumps(self.row(i, float(i), float(i * 2)), sort_keys=True) + "\n"
                for i in range(1, count + 1)
            ),
            encoding="utf-8",
        )

    def ack(self, payload):
        return {
            "stored": True,
            "duplicate": False,
            "observation_id": sync._observation_id(payload["event"]),
            "semantic_projection": False,
            "backend": "sqlite",
        }

    def test_multiple_moves_are_one_structural_trajectory(self) -> None:
        self.write_rows(6)
        sent = []

        def send(payload):
            sent.append(payload)
            return self.ack(payload)

        result = sync.sync_once(
            delta_path=self.delta,
            world_path=self.world,
            checkpoint_path=self.checkpoint,
            send=send,
            max_events=4,
            moves_per_event=16,
        )
        self.assertEqual(result["emitted"], 1)
        self.assertEqual(result["segments"], 5)
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(sent[0]["event"]["trail"]), 6)
        self.assertEqual(sent[0]["provenance"]["segment_count"], 5)
        self.assertEqual(
            sent[0]["provenance"]["source_kind"],
            "confirmed_world_delta_trajectory",
        )
        self.assertTrue(
            sent[0]["provenance"]["hierarchy_id"].endswith(":nov:trajectory-v2")
        )

    def test_checkpoint_advances_after_each_ack_even_if_next_batch_fails(self) -> None:
        self.write_rows(8)
        calls = 0

        def send(payload):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise sync.SpatialMemorySyncError("synthetic_failure")
            return self.ack(payload)

        with self.assertRaisesRegex(sync.SpatialMemorySyncError, "synthetic_failure"):
            sync.sync_once(
                delta_path=self.delta,
                world_path=self.world,
                checkpoint_path=self.checkpoint,
                send=send,
                max_events=4,
                moves_per_event=3,
            )

        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["last_sequence"], 4)
        self.assertEqual(checkpoint["last_position"], {"x": 4.0, "y": 8.0})

        sent = []
        result = sync.sync_once(
            delta_path=self.delta,
            world_path=self.world,
            checkpoint_path=self.checkpoint,
            send=lambda payload: (sent.append(payload) or self.ack(payload)),
            max_events=4,
            moves_per_event=3,
        )
        self.assertGreaterEqual(result["segments"], 1)
        self.assertTrue(sent)
        self.assertEqual(sent[0]["provenance"]["path_sequences"][0], 4)


if __name__ == "__main__":
    unittest.main()
