from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "cognitive_terrain_projection.py"
spec = importlib.util.spec_from_file_location("cognitive_terrain_projection_008b", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


class CognitiveTerrain008BTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.world = self.root / "world.json"
        self.checkpoint = self.root / "checkpoint.json"
        self.db = self.root / "external-episodes.sqlite3"
        self.output = self.root / "projection.json"
        self.world_id = "world-test"
        self.regions = [
            {"id": "clearing", "center": {"x": 640.0, "y": 360.0}, "radius": 140, "biome": "clearing"},
            {"id": "ridge", "center": {"x": 500.0, "y": 220.0}, "radius": 120, "biome": "hills"},
            {"id": "meadow", "center": {"x": 760.0, "y": 560.0}, "radius": 130, "biome": "meadow"},
            {"id": "river", "center": {"x": 800.0, "y": 360.0}, "radius": 110, "biome": "river"},
        ]
        self.world.write_text(json.dumps({
            "world_id": self.world_id,
            "regions": self.regions,
            "sequence": 10,
        }), encoding="utf-8")
        self.db.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db)
        db.execute(
            "CREATE TABLE observations ("
            "record_key TEXT PRIMARY KEY, content_sha256 TEXT NOT NULL, source_json TEXT NOT NULL,"
            "evidence_id TEXT NOT NULL, world_id TEXT NOT NULL, episode_id TEXT NOT NULL,"
            "logical_tick INTEGER NOT NULL)"
        )
        db.commit()
        db.close()
        self.keys: list[tuple[str, str]] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _episode(self, *, tick: int, region: str, need: str = "explore") -> None:
        episode_id = f"plan:p-{tick}"
        source = {
            "system": "live.infinita",
            "world_id": self.world_id,
            "entity_id": "nov",
            "episode_id": episode_id,
        }
        record_key = sha256(canonical(source)).hexdigest()
        payload = {
            "schema": "live-infinita-npc-episode-observation/v1",
            "record_key": record_key,
            "source": {**source, "plan_id": f"p-{tick}"},
            "observation": {
                "logical_tick": tick,
                "need": need,
                "target_entity_id": "target",
                "strategy_id": "strategy",
                "context": {
                    "period": "day",
                    "weather": "clear",
                    "region_id": region,
                    "danger_level": 0.1,
                },
                "outcome": {
                    "satisfaction": 0.7,
                    "observed_risk": 0.1,
                    "elapsed_ticks": 2,
                    "preemptions": 0,
                    "replans": 0,
                },
            },
            "authority": "observed-outcome-only",
            "world_write_authority": False,
        }
        source_json = canonical(payload).decode("utf-8")
        digest = sha256(source_json.encode("utf-8")).hexdigest()
        db = sqlite3.connect(self.db)
        db.execute(
            "INSERT INTO observations VALUES (?,?,?,?,?,?,?)",
            (record_key, digest, source_json, "evidence:" + record_key[:12],
             self.world_id, episode_id, tick),
        )
        db.commit()
        db.close()
        self.keys.append((record_key, digest))

    def _finish_checkpoint(self) -> None:
        key, digest = self.keys[-1]
        self.checkpoint.write_text(json.dumps({
            "schema": module.CHECKPOINT_SCHEMA,
            "world_id": self.world_id,
            "cursor": len(self.keys),
            "last_acked_record_key": key,
            "last_acked_content_sha256": digest,
            "ledger_identity": "test",
            "prefix_sha256": "0" * 64,
            "last_line_sha256": "1" * 64,
        }), encoding="utf-8")

    def test_projection_is_deterministic_bounded_and_non_authoritative(self) -> None:
        for tick, region in [
            (10, "clearing"), (20, "ridge"), (30, "clearing"),
            (40, "ridge"), (50, "clearing"), (60, "meadow"),
            (70, "clearing"),
        ]:
            self._episode(tick=tick, region=region)
        self._finish_checkpoint()

        first = module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        raw_a = self.output.read_bytes()
        projection = json.loads(raw_a)
        second = module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        raw_b = self.output.read_bytes()

        self.assertEqual(first["projection_id"], second["projection_id"])
        self.assertEqual(raw_a, raw_b)
        self.assertEqual(projection["schema"], module.SCHEMA)
        self.assertFalse(projection["policy"]["world_write_authority"])
        self.assertFalse(projection["policy"]["selection_authority"])
        self.assertTrue(projection["policy"]["visual_only"])
        self.assertLessEqual(len(projection["regions"]), module.MAX_REGIONS)
        self.assertLessEqual(len(projection["transitions"]), module.MAX_TRANSITIONS)
        self.assertNotIn("record_key", raw_a.decode("utf-8"))
        self.assertNotIn("target_entity_id", raw_a.decode("utf-8"))
        self.assertNotIn("strategy_id", raw_a.decode("utf-8"))

    def test_recurrence_creates_uplift_and_low_memory_region_creates_basin(self) -> None:
        for tick, region in [
            (10, "clearing"), (20, "ridge"), (30, "clearing"),
            (40, "ridge"), (50, "clearing"), (60, "clearing"),
        ]:
            self._episode(tick=tick, region=region)
        self._finish_checkpoint()
        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        rows = {
            row["region_id"]: row
            for row in json.loads(self.output.read_text(encoding="utf-8"))["regions"]
        }
        self.assertEqual(rows["clearing"]["terrain_role"], "uplift")
        self.assertGreater(rows["clearing"]["elevation_bias_m"], 0)
        basin = [row for row in rows.values() if row["terrain_role"] == "basin"]
        self.assertEqual(len(basin), 1)
        self.assertNotEqual(basin[0]["biome"], "river")
        self.assertLess(basin[0]["elevation_bias_m"], 0)

    def test_transitions_capture_temporal_region_path_without_raw_payload(self) -> None:
        for tick, region in [
            (10, "clearing"), (20, "ridge"), (30, "clearing"),
            (40, "ridge"), (50, "meadow"),
        ]:
            self._episode(tick=tick, region=region)
        self._finish_checkpoint()
        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        projection = json.loads(self.output.read_text(encoding="utf-8"))
        transitions = {
            (row["from_region_id"], row["to_region_id"]): row
            for row in projection["transitions"]
        }
        self.assertEqual(transitions[("clearing", "ridge")]["count"], 2)
        self.assertEqual(transitions[("ridge", "clearing")]["count"], 1)
        self.assertGreater(transitions[("clearing", "ridge")]["ridge_height_m"], 1.0)

    def test_transient_sqlite_writer_lock_is_retried_without_losing_projection(self) -> None:
        self._episode(tick=10, region="clearing")
        self._finish_checkpoint()

        lock = sqlite3.connect(self.db, timeout=0.0, check_same_thread=False)
        lock.execute("BEGIN EXCLUSIVE")

        released = threading.Event()

        def release_lock() -> None:
            time.sleep(0.15)
            lock.rollback()
            lock.close()
            released.set()

        worker = threading.Thread(target=release_lock, daemon=True)
        worker.start()

        old_timeout = module.SQLITE_BUSY_TIMEOUT_SECONDS
        old_retries = module.SQLITE_READ_RETRIES
        old_delay = module.SQLITE_RETRY_BASE_SECONDS
        try:
            module.SQLITE_BUSY_TIMEOUT_SECONDS = 0.03
            module.SQLITE_READ_RETRIES = 6
            module.SQLITE_RETRY_BASE_SECONDS = 0.02
            result = module._project_with_busy_retry(
                db_path=self.db,
                checkpoint_path=self.checkpoint,
                world_path=self.world,
                output_path=self.output,
            )
        finally:
            module.SQLITE_BUSY_TIMEOUT_SECONDS = old_timeout
            module.SQLITE_READ_RETRIES = old_retries
            module.SQLITE_RETRY_BASE_SECONDS = old_delay
            worker.join(timeout=2.0)

        self.assertTrue(released.is_set())
        self.assertEqual(result["status"], "ok")
        projection = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(projection["projection_id"], result["projection_id"])

    def test_corrupt_memoria_digest_fails_closed_and_does_not_write_projection(self) -> None:
        self._episode(tick=10, region="clearing")
        self._finish_checkpoint()
        db = sqlite3.connect(self.db)
        db.execute("UPDATE observations SET content_sha256=?", ("f" * 64,))
        db.commit()
        db.close()
        with self.assertRaisesRegex(module.CognitiveTerrainError, "checkpoint_watermark_missing|memory_digest_mismatch"):
            module.project_once(
                db_path=self.db, checkpoint_path=self.checkpoint,
                world_path=self.world, output_path=self.output,
            )
        self.assertFalse(self.output.exists())

    def test_unknown_memory_regions_do_not_become_visual_authority(self) -> None:
        self._episode(tick=10, region="unknown-memory-place")
        self._finish_checkpoint()
        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        projection = json.loads(self.output.read_text(encoding="utf-8"))
        rows = {row["region_id"]: row for row in projection["regions"]}
        self.assertEqual(set(rows), {"clearing", "ridge", "meadow", "river"})
        self.assertTrue(all(row["visits"] == 0 for row in rows.values()))
        self.assertFalse(projection["policy"]["world_write_authority"])

    def test_visual_projection_persists_and_converges_across_timer_cycles(self) -> None:
        self._episode(tick=10, region="clearing")
        self._finish_checkpoint()
        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        baseline = json.loads(self.output.read_text(encoding="utf-8"))

        # Strengthen the same cognitive structure substantially.
        tick = 20
        for region in [
            "ridge", "clearing", "ridge", "clearing", "ridge",
            "clearing", "ridge", "clearing", "ridge", "clearing",
        ]:
            self._episode(tick=tick, region=region)
            tick += 10
        self._finish_checkpoint()

        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        step1 = json.loads(self.output.read_text(encoding="utf-8"))
        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        step2 = json.loads(self.output.read_text(encoding="utf-8"))

        self.assertNotEqual(
            baseline["projection_id"],
            step1["projection_id"],
        )
        self.assertEqual(
            step1["projection_id"],
            step2["projection_id"],
        )
        self.assertNotEqual(
            step1["visual_projection_id"],
            step2["visual_projection_id"],
        )

        raw1 = {
            row["region_id"]: row for row in step1["regions"]
        }["clearing"]
        visual1 = {
            row["region_id"]: row for row in step1["visual_regions"]
        }["clearing"]
        visual2 = {
            row["region_id"]: row for row in step2["visual_regions"]
        }["clearing"]

        self.assertNotEqual(
            visual1["elevation_bias_m"],
            raw1["elevation_bias_m"],
        )
        self.assertLessEqual(
            abs(
                visual2["elevation_bias_m"]
                - raw1["elevation_bias_m"]
            ),
            abs(
                visual1["elevation_bias_m"]
                - raw1["elevation_bias_m"]
            ),
        )
        self.assertEqual(
            step1["visual_stability"]["refresh_hint_seconds"],
            120,
        )

    def test_projection_reader_accepts_only_matching_visual_side_channel(self) -> None:
        self._episode(tick=10, region="clearing")
        self._finish_checkpoint()
        module.project_once(
            db_path=self.db, checkpoint_path=self.checkpoint,
            world_path=self.world, output_path=self.output,
        )
        reader = module.CognitiveTerrainProjectionReader(self.output)
        first = reader.read(self.world_id)
        second = reader.read(self.world_id)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        with self.assertRaisesRegex(module.CognitiveTerrainError, "projection_contract"):
            reader.read("another-world")

    def test_runtime_attaches_projection_to_delivery_not_world_state(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "main_spatial.py").read_text(encoding="utf-8")
        self.assertIn('delivery["cognitive_terrain"] = projection', source)
        self.assertIn("CognitiveTerrainProjectionReader", source)
        self.assertNotIn('payload["world"]["cognitive_terrain"]', source)
        self.assertNotIn('message["world"]["cognitive_terrain"]', source)

    def test_projection_service_is_local_read_only_and_resource_bounded(self) -> None:
        service = (ROOT / "deploy" / "live-infinita-cognitive-terrain.service").read_text(encoding="utf-8")
        timer = (ROOT / "deploy" / "live-infinita-cognitive-terrain.timer").read_text(encoding="utf-8")
        self.assertIn("IPAddressDeny=any", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ReadOnlyPaths=/var/lib/live-infinita/memoria-local", service)
        self.assertIn("ReadOnlyPaths=/var/lib/live-infinita/autonomous-world", service)
        self.assertIn("ReadWritePaths=/var/lib/live-infinita/cognitive-terrain", service)
        self.assertIn("MemoryMax=256M", service)
        self.assertNotIn("EnvironmentFile=", service)
        self.assertIn("OnUnitInactiveSec=2min", timer)
        self.assertIn("Persistent=false", timer)

    def test_rollout_has_backup_rollback_health_and_preview_gate(self) -> None:
        script = (ROOT / "deploy" / "apply-cognitive-terrain-008b.sh").read_text(encoding="utf-8")
        self.assertIn("rollback()", script)
        self.assertIn("backup_one()", script)
        self.assertIn("restore_one()", script)
        self.assertIn("systemctl start live-infinita-cognitive-terrain.service", script)
        self.assertIn("systemctl restart live-infinita.service", script)
        self.assertIn("replay_ok", script)
        self.assertIn("export-world-map-preview-web.sh", script)
        self.assertIn('"world_write_authority"] is False', script)
        self.assertNotIn("live-infinita-autonomous-world.service", script)
        self.assertNotIn("npc-episodes.jsonl", script)


if __name__ == "__main__":
    unittest.main()
