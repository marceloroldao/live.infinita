from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "migrate_world_to_cold.py"
spec = importlib.util.spec_from_file_location("migrate_world_to_cold_test_module", TOOLS)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["migrate_world_to_cold_test_module"] = module
spec.loader.exec_module(module)


class MigrateWorldToColdTest(unittest.TestCase):
    def _world(self) -> dict:
        return {
            "world_id": "regional",
            "version": 1,
            "sequence": 0,
            "regions": [{"id": "r0", "center": {"x": 0, "y": 0}, "radius": 100, "neighbors": []}],
            "entities": [{"id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0}}],
            "environment": {"biome": "forest"},
        }

    def test_dry_run_does_not_mutate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world_file = root / "world.json"
            backup_file = root / "world.backup.json"
            cold_dir = root / "cold"
            original = self._world()
            world_file.write_text(json.dumps(original), encoding="utf-8")
            report = module.migrate(world_file=world_file, cold_store_dir=cold_dir, backup_file=backup_file, dry_run=True)
            self.assertTrue(report["ok"])
            self.assertFalse(backup_file.exists())
            self.assertFalse(cold_dir.exists())
            self.assertEqual(json.loads(world_file.read_text(encoding="utf-8")), original)

    def test_migration_creates_backup_manifest_and_empty_resident_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world_file = root / "world.json"
            backup_file = root / "world.backup.json"
            cold_dir = root / "cold"
            original = self._world()
            world_file.write_text(json.dumps(original), encoding="utf-8")
            report = module.migrate(world_file=world_file, cold_store_dir=cold_dir, backup_file=backup_file)
            migrated = json.loads(world_file.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertTrue(backup_file.exists())
            self.assertEqual(json.loads(backup_file.read_text(encoding="utf-8")), original)
            self.assertEqual(migrated["entities"], [])
            self.assertEqual(migrated["cold_entities"]["entities_total"], 1)
            self.assertTrue((cold_dir / "manifest.json").exists())

    def test_missing_region_id_is_rejected(self) -> None:
        world = self._world()
        world["entities"][0].pop("region_id")
        with self.assertRaises(ValueError):
            module.validate_source_world(world)

    def test_legacy_history_blocks_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world_file = root / "world.json"
            world_file.write_text(json.dumps(self._world()), encoding="utf-8")
            (root / "deltas.jsonl").write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                module.migrate(
                    world_file=world_file,
                    cold_store_dir=root / "cold",
                    backup_file=root / "backup.json",
                )


if __name__ == "__main__":
    unittest.main()
