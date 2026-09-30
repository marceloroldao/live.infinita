#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from autonomous_runtime import region_catalog_from_world
from cold_engine import ColdAuthoritativeWorldEngine
from packages.spatial import FileRegionColdStore


def _load_json(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _region_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "").strip()


def merge_regions(current: list[dict[str, Any]], target: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_by_id = {_region_id(row): deepcopy(row) for row in current if isinstance(row, dict) and _region_id(row)}
    target_by_id = {_region_id(row): deepcopy(row) for row in target if isinstance(row, dict) and _region_id(row)}
    if len(target_by_id) != len(target):
        raise ValueError("target topology contains invalid or duplicate region ids")

    merged: list[dict[str, Any]] = []
    for target_row in target:
        region_id = _region_id(target_row)
        previous = current_by_id.get(region_id, {})
        row = deepcopy(target_row)
        previous_neighbors = {str(v) for v in previous.get("neighbors", []) if str(v)}
        target_neighbors = {str(v) for v in row.get("neighbors", []) if str(v)}
        row["neighbors"] = sorted(previous_neighbors | target_neighbors)
        previous_metadata = previous.get("metadata") if isinstance(previous.get("metadata"), dict) else {}
        target_metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        row["metadata"] = {**deepcopy(previous_metadata), **deepcopy(target_metadata)}
        merged.append(row)

    for region_id in sorted(set(current_by_id) - set(target_by_id)):
        merged.append(current_by_id[region_id])

    known = {_region_id(row) for row in merged}
    for row in merged:
        missing = sorted({str(v) for v in row.get("neighbors", []) if str(v)} - known)
        if missing:
            raise ValueError(f"region {_region_id(row)} references unknown neighbors: {','.join(missing)}")

    region_catalog_from_world({"regions": merged})
    return merged


def _canonical_regions(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def apply_topology(
    *,
    topology_file: Path,
    bootstrap_file: Path,
    data_dir: Path,
    cold_store_dir: Path,
    source: str = "deploy-nov-topology-006",
    merge_existing: bool = True,
) -> dict[str, Any]:
    topology = _load_json(topology_file)
    target = topology.get("regions")
    if not isinstance(target, list) or not target:
        raise ValueError("topology file requires non-empty regions")

    store = FileRegionColdStore(cold_store_dir)
    engine = ColdAuthoritativeWorldEngine(bootstrap_file, data_dir, store)
    current = engine.load_world()
    current_regions = current.get("regions")
    if not isinstance(current_regions, list) or not current_regions:
        raise ValueError("authoritative world has no regions")

    merged = merge_regions(current_regions, target) if merge_existing else deepcopy(target)
    region_catalog_from_world({"regions": merged})
    if _canonical_regions(current_regions) == _canonical_regions(merged):
        return {
            "status": "already_applied",
            "sequence": int(current.get("sequence", 0)),
            "regions_total": len(merged),
            "state_hash": str(current.get("state_hash") or ""),
        }

    narration = ""
    if isinstance(current.get("narration"), dict):
        narration = str(current["narration"].get("text") or "")

    _, delta, world = engine.commit_operations(
        [{"op": "set_world", "path": ["regions"], "value": merged}],
        source=source,
        context={
            "topology_schema": str(topology.get("schema") or ""),
            "topology_file": topology_file.name,
            "target_regions": len(target),
            "preserved_regions": max(0, len(merged) - len(target)) if merge_existing else 0,
            "merge_existing": merge_existing,
        },
        narration=narration,
    )
    return {
        "status": "applied",
        "sequence": int(world.get("sequence", 0)),
        "delta_id": delta.get("delta_id"),
        "regions_total": len(merged),
        "state_hash": str(world.get("state_hash") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology-file", type=Path, default=ROOT / "examples" / "nov-world-regions-005.json")
    parser.add_argument("--bootstrap-file", type=Path, default=Path(os.getenv("LIVE_INFINITA_COLD_BOOTSTRAP_FILE", "")))
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("LIVE_INFINITA_DATA_DIR", "")))
    parser.add_argument("--cold-store-dir", type=Path, default=Path(os.getenv("LIVE_INFINITA_COLD_STORE_DIR", "")))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--replace-exact", action="store_true")
    parser.add_argument("--source", default="deploy-nov-topology-006")
    args = parser.parse_args()

    if not args.topology_file.exists():
        raise SystemExit("topology-file is required")
    topology = _load_json(args.topology_file)
    target = topology.get("regions")
    if not isinstance(target, list) or not target:
        raise SystemExit("topology file requires non-empty regions")
    region_catalog_from_world({"regions": target})

    if not args.apply:
        print(json.dumps({
            "status": "validated",
            "target_regions": len(target),
            "topology_file": str(args.topology_file),
        }, ensure_ascii=False, sort_keys=True))
        return 0

    for name, value in (
        ("bootstrap-file", args.bootstrap_file),
        ("data-dir", args.data_dir),
        ("cold-store-dir", args.cold_store_dir),
    ):
        if not str(value) or str(value) == ".":
            raise SystemExit(f"{name} is required")

    result = apply_topology(
        topology_file=args.topology_file,
        bootstrap_file=args.bootstrap_file,
        data_dir=args.data_dir,
        cold_store_dir=args.cold_store_dir,
        source=args.source,
        merge_existing=not args.replace_exact,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
