from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "nov_spatial_memory_sync.py"
spec = importlib.util.spec_from_file_location("nov_spatial_memory_sync_008s", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SpatialMemorySync008STests(unittest.TestCase):
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
    def _row(sequence: int, x: float, y: float, region: str) -> dict:
        return {
            "event_id": f"evt_{sequence}",
            "sequence": sequence,
            "result_hash": ("%064x" % sequence)[-64:],
            "operations": [{
                "op": "move", "entity_id": "nov",
                "position": {"x": x, "y": y}, "region_id": region,
            }],
        }

    def _write_rows(self, rows: list[dict]) -> None:
        self.delta.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_confirmed_moves_become_structural_segments_and_checkpoint(self) -> None:
        self._write_rows([
            self._row(10, 100.0, 200.0, "forest"),
            self._row(11, 108.0, 204.0, "forest"),
            self._row(12, 140.0, 240.0, "hills"),
        ])
        sent = []

        def send(payload):
            sent.append(payload)
            return {
                "stored": True,
                "duplicate": False,
                "observation_id": module._observation_id(payload["event"]),
                "association_sync_observations": 0,
                "association_sync_deferred": True,
                "semantic_projection": False,
                "backend": "sqlite",
            }

        result = module.sync_once(
            delta_path=self.delta, world_path=self.world,
            checkpoint_path=self.checkpoint, send=send,
        )
        self.assertEqual(result["emitted"], 1)
        self.assertEqual(result["stored"], 1)
        self.assertEqual(result["segments"], 2)
        self.assertEqual(len(sent), 1)
        first = sent[0]
        self.assertEqual(first["event"]["trail"], [
            module._cell_id({"x": 100.0, "y": 200.0}),
            module._cell_id({"x": 108.0, "y": 204.0}),
            module._cell_id({"x": 140.0, "y": 240.0}),
        ])
        self.assertEqual(first["provenance"]["from_position"], {"x": 100.0, "y": 200.0})
        self.assertEqual(first["provenance"]["to_position"], {"x": 140.0, "y": 240.0})
        self.assertEqual(first["provenance"]["segment_count"], 2)
        self.assertEqual(first["provenance"]["authority"], "observed-world-delta")
        self.assertFalse(first["provenance"]["world_write_authority"])

        checkpoint = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["last_sequence"], 12)
        self.assertEqual(checkpoint["last_position"], {"x": 140.0, "y": 240.0})

        again = module.sync_once(
            delta_path=self.delta, world_path=self.world,
            checkpoint_path=self.checkpoint, send=send,
        )
        self.assertEqual(again["emitted"], 0)
        self.assertEqual(len(sent), 1)

    def test_checkpoint_detects_rewritten_source_tail(self) -> None:
        self._write_rows([
            self._row(10, 1.0, 2.0, "a"),
            self._row(11, 3.0, 4.0, "b"),
        ])

        def send(payload):
            return {
                "stored": True, "duplicate": False,
                "observation_id": module._observation_id(payload["event"]),
                "association_sync_deferred": True,
                "semantic_projection": False, "backend": "sqlite",
            }
        module.sync_once(
            delta_path=self.delta, world_path=self.world,
            checkpoint_path=self.checkpoint, send=send,
        )
        rows = self.delta.read_text(encoding="utf-8").splitlines()
        rows[-1] = json.dumps(self._row(11, 99.0, 99.0, "b"), sort_keys=True)
        self.delta.write_text("\n".join(rows) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(module.SpatialMemorySyncError, "checkpoint_source_changed|checkpoint_not_line_boundary"):
            module.sync_once(
                delta_path=self.delta, world_path=self.world,
                checkpoint_path=self.checkpoint, send=send,
            )

    def test_non_nov_delta_is_ignored_without_fabricating_a_path(self) -> None:
        row = self._row(10, 1.0, 2.0, "a")
        row["operations"][0]["entity_id"] = "other"
        self._write_rows([row])
        sent = []
        result = module.sync_once(
            delta_path=self.delta, world_path=self.world,
            checkpoint_path=self.checkpoint, send=lambda payload: sent.append(payload),
        )
        self.assertEqual(result["emitted"], 0)
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
