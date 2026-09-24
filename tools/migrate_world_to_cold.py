from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cold_engine import ColdAuthoritativeWorldEngine
from packages.spatial import FileRegionColdStore, externalize_world_entities


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    tmp.replace(path)


def validate_source_world(world: dict) -> None:
    entities = [row for row in world.get("entities", []) if isinstance(row, dict)]
    regions = [row for row in world.get("regions", []) if isinstance(row, dict)]
    if not entities:
        raise ValueError("source world has no resident entities to migrate")
    if not regions:
        raise ValueError("source world requires explicit regions before cold migration")
    region_ids = {str(row.get("id", "")).strip() for row in regions}
    if "" in region_ids:
        raise ValueError("all regions require an id")
    for entity in entities:
        entity_id = str(entity.get("id", "")).strip()
        region_id = str(entity.get("region_id", "")).strip()
        if not entity_id:
            raise ValueError("all entities require an id")
        if not region_id:
            raise ValueError(f"entity {entity_id} has no region_id")
        if region_id not in region_ids:
            raise ValueError(f"entity {entity_id} references unknown region {region_id}")


def migrate(*, world_file: Path, cold_store_dir: Path, backup_file: Path, dry_run: bool = False) -> dict:
    world = _load(world_file)
    validate_source_world(world)
    if world.get("cold_entities"):
        raise ValueError("world already declares cold_entities")

    data_dir = world_file.parent
    for name in ("events.jsonl", "deltas.jsonl"):
        path = data_dir / name
        if path.exists() and path.stat().st_size > 0:
            raise ValueError(f"refusing migration with legacy history present: {name}")

    entities_total = len([row for row in world.get("entities", []) if isinstance(row, dict)])
    regions_total = len([row for row in world.get("regions", []) if isinstance(row, dict)])
    report = {
        "ok": True,
        "dry_run": dry_run,
        "entities_total": entities_total,
        "regions_total": regions_total,
        "world_file": str(world_file),
        "backup_file": str(backup_file),
        "cold_store_dir": str(cold_store_dir),
    }
    if dry_run:
        return report

    if backup_file.exists():
        raise ValueError(f"backup already exists: {backup_file}")
    if cold_store_dir.exists() and any(cold_store_dir.iterdir()):
        raise ValueError("cold store directory must be empty for migration")

    backup_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(world_file, backup_file)
    store = FileRegionColdStore(cold_store_dir)
    migrated = externalize_world_entities(world, store)
    migrated["version"] = int(world.get("version", 0))
    migrated["sequence"] = int(world.get("sequence", 0))
    migrated["state_hash"] = ColdAuthoritativeWorldEngine._bootstrap_hash(migrated)
    _save(world_file, migrated)
    report["state_hash"] = migrated["state_hash"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate an explicitly regionalized Live Infinita world to cold storage.")
    parser.add_argument("--world-file", required=True, type=Path)
    parser.add_argument("--cold-store-dir", required=True, type=Path)
    parser.add_argument("--backup-file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        report = migrate(
            world_file=args.world_file,
            cold_store_dir=args.cold_store_dir,
            backup_file=args.backup_file,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
