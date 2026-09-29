"""MVP-018L: consistent READ-ONLY current Nov frame from cold-backed world.

Must run as the authorised owner. Never instantiate the world engine or
FileRegionColdStore: those constructors may create directories or mutate state.
Take the existing Single Writer mutation lock in shared, nonblocking mode
while reading a bounded world envelope, manifest and one region payload.
"""
from __future__ import annotations

import fcntl
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from memoria_v2_adapter import CognitiveFrame, build_nov_cognitive_frame
from nov_memory_recall_shadow import MAX_WORLD_BYTES, RecallBlocked, _read_bounded_json

MAX_MANIFEST_BYTES = 64 * 1024
MAX_REGION_BYTES = 256 * 1024


def _bounded_array(path: Path, limit: int) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise RecallBlocked("current_region_unavailable")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise RecallBlocked("current_region_oversized")
    try:
        rows = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise RecallBlocked("current_region_invalid") from exc
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise RecallBlocked("current_region_invalid")
    return rows


def sample_current_nov_frame(
    *, world_path: Path, cold_root: Path, mutation_lock: Path,
) -> CognitiveFrame:
    """Observed current world+Nov entity, never latest remembered episode."""
    if (world_path.is_symlink() or cold_root.is_symlink()
            or mutation_lock.is_symlink() or not mutation_lock.is_file()
            or world_path.parent != mutation_lock.parent
            or cold_root != world_path.parent / "cold-store"):
        raise RecallBlocked("current_frame_path_invalid")
    with mutation_lock.open("rb") as guard:
        try:
            fcntl.flock(guard.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RecallBlocked("current_world_commit_busy") from exc
        try:
            _, world = _read_bounded_json(world_path, MAX_WORLD_BYTES, "current_world")
            world_id = world.get("world_id")
            tick = world.get("current_tick", world.get("sequence"))
            sequence = world.get("sequence")
            version = world.get("version")
            cold = world.get("cold_entities")
            if (not isinstance(world_id, str) or not world_id
                    or type(tick) is not int or tick < 0
                    or type(sequence) is not int or sequence < 0
                    or type(version) is not int or version < 0
                    or not isinstance(world.get("environment"), dict)
                    or not isinstance(cold, dict)
                    or cold.get("mode") != "region_file_store"
                    or world.get("entities") not in ([], None)):
                raise RecallBlocked("current_world_contract")
            _, manifest = _read_bounded_json(
                cold_root / "manifest.json", MAX_MANIFEST_BYTES, "current_manifest",
            )
            if type(manifest.get("version")) is not int or manifest["version"] != 1:
                raise RecallBlocked("current_manifest_version")
            mapping = manifest.get("entity_region")
            region = mapping.get("nov") if isinstance(mapping, dict) else None
            if not isinstance(region, str) or not region or len(region) > 160:
                raise RecallBlocked("current_nov_region_unavailable")
            region_path = cold_root / "regions" / (
                sha256(region.encode("utf-8")).hexdigest() + ".json"
            )
            observed = [
                row for row in _bounded_array(region_path, MAX_REGION_BYTES)
                if row.get("id") == "nov"
            ]
            if (len(observed) != 1 or observed[0].get("region_id") != region
                    or not isinstance(observed[0].get("properties"), dict)):
                raise RecallBlocked("current_nov_entity_inconsistent")
            frame = build_nov_cognitive_frame(
                world=world, observer=observed[0], targets={},
            )
            if frame.tick_id != tick or frame.observer_id != "nov":
                raise RecallBlocked("current_frame_tick_mismatch")
            return frame
        finally:
            fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
