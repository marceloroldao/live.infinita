from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "cognitive_terrain_projection.py"
spec = importlib.util.spec_from_file_location("cognitive_terrain_projection_008s", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CognitiveSpatialMemory008STests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = self.root / "index.jsonl"
        self.db = self.root / "persistence" / "memoria.sqlite3"
        self.db.parent.mkdir(parents=True)
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE memories(memory_id TEXT PRIMARY KEY,payload BLOB NOT NULL)")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _store(self, *, sequence: int, trail: list[int], start: tuple[float, float], end: tuple[float, float]) -> None:
        event = {
            "version": 1,
            "source_id": "live.infinita:world-test:nov:movement",
            "sequence": sequence,
            "byte_offset": sequence * 10,
            "byte_length": 100,
            "trail": trail,
            "relation_ids": [77],
            "signature": ("%016x" % sequence)[-16:],
            "resolution": 4,
        }
        observation_id = f"structural-event:test-{sequence}"
        envelope = {
            "format": "memoria.ia-structural-observation-v1",
            "observation_id": observation_id,
            "event": event,
            "provenance": {
                "hierarchy_id": "live:spatial:world-test:nov",
                "source_kind": "confirmed_world_delta_move",
                "source_ledger": "deltas.jsonl",
                "world_id": "world-test",
                "entity_id": "nov",
                "authority": "observed-world-delta",
                "world_write_authority": False,
                "world_sequence": sequence,
                "world_event_id": f"evt_{sequence}",
                "result_hash": ("%064x" % sequence)[-64:],
                "spatial_resolution_m": 4.0,
                "from_position": {"x": start[0], "y": start[1]},
                "to_position": {"x": end[0], "y": end[1]},
                "from_region_id": "forest",
                "to_region_id": "hills",
            },
            "semantic_projection": False,
        }
        payload = module._canonical(envelope)
        digest = sha256(payload).hexdigest()
        state_id = "structural-observation:" + digest
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO memories VALUES (?,?)", (state_id, payload))
        conn.commit()
        conn.close()
        row = {
            "format": "memoria.ia-structural-observation-index-v1",
            "observation_id": observation_id,
            "receipt": {"backend": "sqlite", "state_id": state_id, "sha256": digest},
        }
        with self.index.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def test_reader_accepts_only_verified_spatial_memoria_rows(self) -> None:
        self._store(sequence=10, trail=[101, 202], start=(10.0, 20.0), end=(30.0, 40.0))
        rows = module._validated_spatial_rows(self.index, self.db, "world-test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trail"], (101, 202))
        self.assertEqual(rows[0]["from_position"], {"x": 10.0, "y": 20.0})
        self.assertEqual(rows[0]["to_position"], {"x": 30.0, "y": 40.0})

    def test_repeated_spatial_segment_becomes_xy_trail(self) -> None:
        spatial = [
            {"sequence": 10, "trail": (101, 202), "from_position": {"x": 10.0, "y": 20.0},
             "to_position": {"x": 30.0, "y": 40.0}, "from_region_id": "forest", "to_region_id": "hills"},
            {"sequence": 20, "trail": (202, 101), "from_position": {"x": 30.0, "y": 40.0},
             "to_position": {"x": 10.0, "y": 20.0}, "from_region_id": "hills", "to_region_id": "forest"},
        ]
        projection = module.build_projection(
            world_id="world-test",
            known_regions=[
                {"region_id": "forest", "center": {"x": 0.0, "y": 0.0}, "biome": "forest"},
                {"region_id": "hills", "center": {"x": 100.0, "y": 0.0}, "biome": "hills"},
            ],
            records=[],
            source_snapshot_records=0,
            checkpoint_cursor=0,
            spatial_records=spatial,
        )
        self.assertEqual(projection["source"]["spatial_observations"], 2)
        self.assertEqual(len(projection["spatial_trails"]), 1)
        trail = projection["spatial_trails"][0]
        self.assertEqual(trail["count"], 2)
        self.assertTrue(trail["trail_candidate"])
        self.assertEqual(trail["from_position"], {"x": 30.0, "y": 40.0})
        self.assertEqual(trail["to_position"], {"x": 10.0, "y": 20.0})

    def test_renderer_prefers_real_xy_trails_over_regional_fallback(self) -> None:
        source = (ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd").read_text(encoding="utf-8")
        self.assertIn('var spatial_trails = projection.get("spatial_trails", [])', source)
        self.assertIn('var trail_source: Array = _spatial_trails if not _spatial_trails.is_empty() else _ridges', source)
        self.assertIn('flat_projector.call(from_position)', source)
        self.assertIn('flat_projector.call(to_position)', source)

    def test_spatial_memory_never_gains_world_authority(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('provenance.get("world_write_authority") is not False', source)
        self.assertIn('"world_write_authority": False', source)
        self.assertIn('"selection_authority": False', source)


if __name__ == "__main__":
    unittest.main()
