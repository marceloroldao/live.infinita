"""008B: bounded read-only cognitive terrain projection from local Memoria.ia.

The source is the durable, typed external-episode SQLite owned by the local
Memoria.ia instance. This module never imports or opens the World State writer,
never submits an intent, and never gives memory mutation/selection authority.

Only aggregate regional recurrence, causal recency and region transitions leave
this process. Raw episode payloads, record keys and user text are never written
into the visual projection.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from math import exp, sqrt, isfinite
import os
from pathlib import Path
import sqlite3
from typing import Any

SCHEMA = "live-infinita-cognitive-terrain/v1"
CHECKPOINT_SCHEMA = "live-infinita-nov-local-memory-checkpoint/v1"
DEFAULT_DB = Path("/var/lib/live-infinita/memoria-local/external-episodes-incremental/external-episodes.sqlite3")
DEFAULT_CHECKPOINT = Path("/var/lib/live-infinita/memoria-local/nov-ingest.checkpoint.json")
DEFAULT_WORLD = Path("/var/lib/live-infinita/autonomous-world/world.json")
DEFAULT_OUTPUT = Path("/var/lib/live-infinita/cognitive-terrain/projection.json")
DEFAULT_SPATIAL_INDEX = Path("/var/lib/live-infinita/memoria-local/structural-observations/index.jsonl")
DEFAULT_SPATIAL_DB = Path("/var/lib/live-infinita/memoria-local/structural-observations/persistence/memoria.sqlite3")

MAX_WORLD_BYTES = 2 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 16 * 1024
MAX_DB_BYTES = 256 * 1024 * 1024
MAX_RECORDS = 8192
MAX_REGIONS = 32
MAX_TRANSITIONS = 48
MAX_SPATIAL_RECORDS = 4096
MAX_SPATIAL_TRAILS = 128
MAX_SPATIAL_INDEX_WINDOW_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024
WATERLIKE_BIOMES = frozenset({"river", "waterfall"})
BASIN_BIOME_PRIORITY = {"meadow": 0, "forest": 1, "hills": 2, "moor": 3}


class CognitiveTerrainError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _read_json(path: Path, limit: int, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CognitiveTerrainError(f"{label}_unavailable")
    if path.stat().st_size > limit:
        raise CognitiveTerrainError(f"{label}_oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise CognitiveTerrainError(f"{label}_invalid") from exc
    if not isinstance(value, dict):
        raise CognitiveTerrainError(f"{label}_invalid")
    return value


def _world_regions(path: Path) -> tuple[str, list[dict[str, Any]]]:
    world = _read_json(path, MAX_WORLD_BYTES, "world")
    world_id = str(world.get("world_id") or "").strip()
    rows = world.get("regions")
    if not world_id or not isinstance(rows, list):
        raise CognitiveTerrainError("world_contract")
    regions: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        region_id = str(row.get("id") or "").strip()
        center = row.get("center")
        if not region_id or not isinstance(center, dict):
            continue
        try:
            x = float(center["x"])
            y = float(center["y"])
        except (KeyError, TypeError, ValueError):
            continue
        regions.append({
            "region_id": region_id,
            "center": {"x": x, "y": y},
            "biome": str(row.get("biome") or "unknown"),
        })
    regions.sort(key=lambda row: row["region_id"])
    if not regions or len(regions) > MAX_REGIONS:
        raise CognitiveTerrainError("region_budget")
    return world_id, regions


def _checkpoint(path: Path, world_id: str) -> dict[str, Any]:
    value = _read_json(path, MAX_CHECKPOINT_BYTES, "checkpoint")
    if value.get("schema") != CHECKPOINT_SCHEMA or value.get("world_id") != world_id:
        raise CognitiveTerrainError("checkpoint_world_mismatch")
    cursor = value.get("cursor")
    if type(cursor) is not int or cursor < 0:
        raise CognitiveTerrainError("checkpoint_cursor_invalid")
    return value


def _validated_rows(db_path: Path, checkpoint: dict[str, Any], world_id: str) -> tuple[list[dict[str, Any]], int]:
    if db_path.is_symlink() or not db_path.is_file():
        raise CognitiveTerrainError("memory_db_unavailable")
    size = db_path.stat().st_size
    if size <= 0 or size > MAX_DB_BYTES:
        raise CognitiveTerrainError("memory_db_budget")

    uri = db_path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        total = int(db.execute(
            "SELECT COUNT(*) FROM observations WHERE world_id=?", (world_id,)
        ).fetchone()[0])
        if checkpoint["cursor"] > 0:
            key = checkpoint.get("last_acked_record_key")
            digest = checkpoint.get("last_acked_content_sha256")
            if not isinstance(key, str) or not isinstance(digest, str):
                raise CognitiveTerrainError("checkpoint_watermark_invalid")
            row = db.execute(
                "SELECT content_sha256 FROM observations WHERE record_key=?", (key,)
            ).fetchone()
            if row != (digest,):
                raise CognitiveTerrainError("checkpoint_watermark_missing")

        rows = db.execute(
            "SELECT record_key,content_sha256,source_json,world_id,episode_id,logical_tick "
            "FROM observations WHERE world_id=? "
            "ORDER BY logical_tick DESC,record_key DESC LIMIT ?",
            (world_id, MAX_RECORDS),
        ).fetchall()
    finally:
        db.close()

    # Work oldest -> newest inside the bounded recent-memory window.
    rows.reverse()
    out: list[dict[str, Any]] = []
    for record_key, digest, source_json, source_world, episode_id, logical_tick in rows:
        if not isinstance(source_json, str):
            raise CognitiveTerrainError("memory_payload_invalid")
        raw = source_json.encode("utf-8")
        if sha256(raw).hexdigest() != digest:
            raise CognitiveTerrainError("memory_digest_mismatch")
        try:
            payload = json.loads(source_json)
        except (ValueError, UnicodeError) as exc:
            raise CognitiveTerrainError("memory_payload_invalid") from exc
        if not isinstance(payload, dict):
            raise CognitiveTerrainError("memory_payload_invalid")

        source = payload.get("source")
        observation = payload.get("observation")
        if not isinstance(source, dict) or not isinstance(observation, dict):
            raise CognitiveTerrainError("memory_contract")
        identity = {
            "system": source.get("system"),
            "world_id": source.get("world_id"),
            "entity_id": source.get("entity_id"),
            "episode_id": source.get("episode_id"),
        }
        expected_key = sha256(_canonical(identity)).hexdigest()
        if (
            expected_key != record_key
            or payload.get("record_key") != record_key
            or source_world != world_id
            or source.get("system") != "live.infinita"
            or source.get("world_id") != world_id
            or source.get("entity_id") != "nov"
            or source.get("episode_id") != episode_id
            or payload.get("schema") != "live-infinita-npc-episode-observation/v1"
            or payload.get("authority") != "observed-outcome-only"
            or payload.get("world_write_authority") is not False
            or type(logical_tick) is not int
            or observation.get("logical_tick") != logical_tick
        ):
            raise CognitiveTerrainError("memory_provenance_mismatch")
        context = observation.get("context")
        if not isinstance(context, dict):
            raise CognitiveTerrainError("memory_context_invalid")
        region_id = context.get("region_id")
        need = observation.get("need")
        out.append({
            "logical_tick": logical_tick,
            "region_id": region_id if isinstance(region_id, str) and region_id else None,
            "need": need if isinstance(need, str) and need else None,
        })
    return out, total


def _recent_index_lines(path: Path, *, limit: int) -> list[bytes]:
    if path.is_symlink():
        raise CognitiveTerrainError("spatial_index_symlink")
    try:
        size = path.stat().st_size
    except (FileNotFoundError, PermissionError):
        # Spatial memory is an optional enhancement. Environments that cannot
        # read its owner-only store retain the verified regional-memory fallback.
        return []
    if not path.is_file() or size <= 0:
        return []
    start = max(0, size - MAX_SPATIAL_INDEX_WINDOW_BYTES)
    with path.open("rb") as fh:
        fh.seek(start)
        data = fh.read(size - start)
    if not data.endswith(b"\n"):
        raise CognitiveTerrainError("spatial_index_torn_tail")
    if start:
        cut = data.find(b"\n")
        data = b"" if cut < 0 else data[cut + 1:]
    return data.splitlines()[-max(1, int(limit)):]


def _position_pair(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise CognitiveTerrainError(label + "_invalid")
    try:
        x, y = float(value["x"]), float(value["y"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise CognitiveTerrainError(label + "_invalid") from exc
    if not isfinite(x) or not isfinite(y) or abs(x) > 10_000_000 or abs(y) > 10_000_000:
        raise CognitiveTerrainError(label + "_invalid")
    return {"x": x, "y": y}


def _validated_spatial_rows(index_path: Path, db_path: Path, world_id: str) -> list[dict[str, Any]]:
    lines = _recent_index_lines(index_path, limit=MAX_SPATIAL_RECORDS)
    if not lines:
        return []
    if db_path.is_symlink() or not db_path.is_file():
        raise CognitiveTerrainError("spatial_store_unavailable")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    rows: list[dict[str, Any]] = []
    try:
        db.execute("PRAGMA query_only=ON")
        for raw in lines:
            try:
                index_row = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise CognitiveTerrainError("spatial_index_invalid") from exc
            if not isinstance(index_row, dict) or index_row.get("format") != "memoria.ia-structural-observation-index-v1":
                raise CognitiveTerrainError("spatial_index_invalid")
            observation_id = str(index_row.get("observation_id") or "")
            receipt = index_row.get("receipt")
            if not observation_id or not isinstance(receipt, dict) or receipt.get("backend") != "sqlite":
                raise CognitiveTerrainError("spatial_receipt_invalid")
            state_id = str(receipt.get("state_id") or "")
            digest = str(receipt.get("sha256") or "")
            if not state_id.startswith("structural-observation:") or len(digest) != 64:
                raise CognitiveTerrainError("spatial_receipt_invalid")
            stored = db.execute("SELECT payload FROM memories WHERE memory_id=?", (state_id,)).fetchone()
            if stored is None:
                raise CognitiveTerrainError("spatial_payload_missing")
            payload = bytes(stored[0])
            if sha256(payload).hexdigest() != digest:
                raise CognitiveTerrainError("spatial_payload_digest")
            try:
                envelope = json.loads(payload)
            except (ValueError, UnicodeError) as exc:
                raise CognitiveTerrainError("spatial_payload_invalid") from exc
            if not isinstance(envelope, dict) or envelope.get("format") != "memoria.ia-structural-observation-v1" or envelope.get("observation_id") != observation_id:
                raise CognitiveTerrainError("spatial_payload_invalid")
            provenance = envelope.get("provenance")
            event = envelope.get("event")
            if not isinstance(provenance, dict) or not isinstance(event, dict):
                raise CognitiveTerrainError("spatial_payload_invalid")
            hierarchy_id = str(provenance.get("hierarchy_id") or "")
            legacy_hierarchy = f"live:spatial:{world_id}:nov"
            trajectory_hierarchy = f"live:spatial:{world_id}:nov:trajectory-v2"
            if hierarchy_id not in {legacy_hierarchy, trajectory_hierarchy}:
                continue
            source_kind = str(provenance.get("source_kind") or "")
            source_id = str(event.get("source_id") or "")
            trail = event.get("trail")
            if (
                provenance.get("world_id") != world_id
                or provenance.get("entity_id") != "nov"
                or source_kind not in {"confirmed_world_delta_move", "confirmed_world_delta_trajectory"}
                or provenance.get("authority") != "observed-world-delta"
                or provenance.get("world_write_authority") is not False
                or type(event.get("sequence")) is not int
                or event.get("sequence") != provenance.get("world_sequence")
                or not isinstance(trail, list)
                or len(trail) < 2
            ):
                raise CognitiveTerrainError("spatial_provenance_mismatch")

            if source_kind == "confirmed_world_delta_move":
                if hierarchy_id != legacy_hierarchy or source_id != f"live.infinita:{world_id}:nov:movement" or len(trail) != 2:
                    raise CognitiveTerrainError("spatial_provenance_mismatch")
                rows.append({
                    "sequence": int(event["sequence"]),
                    "trail": (int(trail[0]), int(trail[1])),
                    "from_position": _position_pair(provenance.get("from_position"), "spatial_from"),
                    "to_position": _position_pair(provenance.get("to_position"), "spatial_to"),
                    "from_region_id": str(provenance.get("from_region_id") or "") or None,
                    "to_region_id": str(provenance.get("to_region_id") or "") or None,
                    "trajectory_v2": False,
                })
                continue

            if hierarchy_id != trajectory_hierarchy or source_id != f"live.infinita:{world_id}:nov:trajectory-v2":
                raise CognitiveTerrainError("spatial_provenance_mismatch")
            positions = provenance.get("path_positions")
            regions = provenance.get("path_region_ids")
            sequences = provenance.get("path_sequences")
            if (
                not isinstance(positions, list)
                or not isinstance(regions, list)
                or not isinstance(sequences, list)
                or len(positions) != len(trail)
                or len(regions) != len(trail)
                or len(sequences) != len(trail)
                or len(trail) < 2
            ):
                raise CognitiveTerrainError("spatial_trajectory_shape")
            clean_positions = [_position_pair(value, "spatial_path") for value in positions]
            for index in range(len(trail) - 1):
                sequence = int(sequences[index + 1])
                if sequence < 0:
                    raise CognitiveTerrainError("spatial_trajectory_sequence")
                rows.append({
                    "sequence": sequence,
                    "trail": (int(trail[index]), int(trail[index + 1])),
                    "from_position": clean_positions[index],
                    "to_position": clean_positions[index + 1],
                    "from_region_id": str(regions[index] or "") or None,
                    "to_region_id": str(regions[index + 1] or "") or None,
                    "trajectory_v2": True,
                })
    finally:
        db.close()
    if any(bool(row.get("trajectory_v2")) for row in rows):
        rows = [row for row in rows if bool(row.get("trajectory_v2"))]
    rows.sort(key=lambda row: row["sequence"])
    return rows


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_projection(
    *, world_id: str, known_regions: list[dict[str, Any]],
    records: list[dict[str, Any]], source_snapshot_records: int,
    checkpoint_cursor: int, spatial_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    known = {row["region_id"]: row for row in known_regions}
    counts: Counter[str] = Counter()
    last_tick: dict[str, int] = {}
    needs: dict[str, set[str]] = defaultdict(set)
    transitions: Counter[tuple[str, str]] = Counter()
    transition_last_tick: dict[tuple[str, str], int] = {}

    ordered = sorted(
        records,
        key=lambda row: (int(row["logical_tick"]), str(row.get("region_id") or "")),
    )
    previous_region: str | None = None
    for row in ordered:
        region = row.get("region_id")
        tick = int(row["logical_tick"])
        if not isinstance(region, str) or region not in known:
            continue
        counts[region] += 1
        last_tick[region] = max(last_tick.get(region, tick), tick)
        need = row.get("need")
        if isinstance(need, str) and need:
            needs[region].add(need)
        if previous_region is not None and previous_region != region:
            edge = (previous_region, region)
            transitions[edge] += 1
            transition_last_tick[edge] = tick
        previous_region = region

    ticks = [int(row["logical_tick"]) for row in ordered]
    max_tick = max(ticks, default=0)
    min_tick = min(ticks, default=max_tick)
    span = max(1, max_tick - min_tick)
    tau = max(32.0, float(span) * 0.20)
    max_count = max(counts.values(), default=1)
    max_transition = max(transitions.values(), default=1)

    incident: Counter[str] = Counter()
    for (source, target), count in transitions.items():
        incident[source] += count
        incident[target] += count
    max_incident = max(incident.values(), default=1)

    masses: dict[str, float] = {}
    base_rows: list[dict[str, Any]] = []
    for region_id, meta in sorted(known.items()):
        visits = counts[region_id]
        count_strength = sqrt(float(visits) / float(max_count)) if visits else 0.0
        recency = exp(-float(max_tick - last_tick[region_id]) / tau) if region_id in last_tick else 0.0
        flux = sqrt(float(incident[region_id]) / float(max_incident)) if incident[region_id] else 0.0
        mass = _clamp(0.60 * count_strength + 0.25 * recency + 0.15 * flux, 0.0, 1.0)
        masses[region_id] = mass
        base_rows.append({
            **meta,
            "visits": visits,
            "last_logical_tick": last_tick.get(region_id),
            "need_variety": len(needs[region_id]),
            "recurrence_strength": round(count_strength, 6),
            "recency_strength": round(recency, 6),
            "transition_flux": round(flux, 6),
            "cognitive_mass": round(mass, 6),
        })

    mean_mass = sum(masses.values()) / max(1, len(masses))
    visited = [rid for rid in masses if counts[rid] > 0]
    uplift_id = max(visited, key=lambda rid: (masses[rid], counts[rid], rid)) if visited else None

    # A basin is a visual mapping hypothesis, not a fact inferred by memory.
    # Prefer terrain biomes where a lake is visually plausible; never place one
    # in village/ruins/cave/highlands just because memory there is sparse.
    basin_candidates = [
        rid for rid, meta in known.items()
        if rid != uplift_id and meta.get("biome") in BASIN_BIOME_PRIORITY
    ]
    basin_id = min(
        basin_candidates,
        key=lambda rid: (
            counts[rid], masses[rid],
            BASIN_BIOME_PRIORITY.get(str(known[rid].get("biome")), 99),
            rid,
        ),
    ) if basin_candidates else None

    regions: list[dict[str, Any]] = []
    for row in base_rows:
        rid = row["region_id"]
        mass = masses[rid]
        elevation = (mass - mean_mass) * 14.0
        role = "memory_field"
        if rid == uplift_id:
            elevation += 8.0
            role = "uplift"
        elif rid == basin_id:
            elevation -= 8.0
            role = "basin"
        elevation = _clamp(elevation, -12.0, 18.0)
        regions.append({
            **row,
            "terrain_role": role,
            "elevation_bias_m": round(elevation, 4),
            "influence_radius_m": round(115.0 + 75.0 * mass, 3),
            "lake_candidate": role == "basin" and elevation <= -6.0,
        })

    transition_rows = []
    for (source, target), count in transitions.most_common(MAX_TRANSITIONS):
        if source not in known or target not in known:
            continue
        strength = sqrt(float(count) / float(max_transition))
        edge_last_tick = transition_last_tick.get((source, target), min_tick)
        edge_recency = exp(-float(max_tick - edge_last_tick) / tau)
        trail_strength = _clamp(strength * edge_recency, 0.0, 1.0)
        transition_rows.append({
            "from_region_id": source,
            "to_region_id": target,
            "count": count,
            "last_logical_tick": edge_last_tick,
            "strength": round(strength, 6),
            "recency_strength": round(edge_recency, 6),
            "trail_strength": round(trail_strength, 6),
            "trail_candidate": count >= 2 and trail_strength >= 0.18,
            "trail_width_m": round(0.7 + 1.8 * trail_strength, 3),
            "ridge_height_m": round(1.0 + 3.5 * strength, 4),
            "ridge_width_m": round(28.0 + 42.0 * strength, 3),
        })

    spatial_records = list(spatial_records or [])
    spatial_counts: Counter[tuple[int, int]] = Counter()
    spatial_last: dict[tuple[int, int], int] = {}
    spatial_sample: dict[tuple[int, int], dict[str, Any]] = {}
    for row in spatial_records:
        trail = row.get("trail")
        if not isinstance(trail, (tuple, list)) or len(trail) != 2:
            continue
        pair = tuple(sorted((int(trail[0]), int(trail[1]))))
        sequence = int(row.get("sequence", 0))
        spatial_counts[pair] += 1
        if sequence >= spatial_last.get(pair, -1):
            spatial_last[pair] = sequence
            spatial_sample[pair] = row

    spatial_trails: list[dict[str, Any]] = []
    if spatial_counts:
        max_spatial_count = max(spatial_counts.values())
        max_spatial_sequence = max(spatial_last.values())
        min_spatial_sequence = min(spatial_last.values())
        spatial_span = max(1, max_spatial_sequence - min_spatial_sequence)
        spatial_tau = max(64.0, float(spatial_span) * 0.20)
        for pair, count in spatial_counts.most_common(MAX_SPATIAL_TRAILS):
            sample = spatial_sample[pair]
            recurrence = sqrt(float(count) / float(max_spatial_count))
            recency = exp(-float(max_spatial_sequence - spatial_last[pair]) / spatial_tau)
            strength = _clamp(recurrence * recency, 0.0, 1.0)
            spatial_trails.append({
                "from_position": sample["from_position"],
                "to_position": sample["to_position"],
                "from_region_id": sample.get("from_region_id"),
                "to_region_id": sample.get("to_region_id"),
                "count": count,
                "last_world_sequence": spatial_last[pair],
                "recurrence_strength": round(recurrence, 6),
                "recency_strength": round(recency, 6),
                "trail_strength": round(strength, 6),
                "trail_candidate": count >= 2 and strength >= 0.18,
                "trail_width_m": round(0.6 + 1.8 * strength, 3),
            })

    basis = {
        "world_id": world_id,
        "checkpoint_cursor": checkpoint_cursor,
        "source_snapshot_records": source_snapshot_records,
        "nov_observations": len(records),
        "latest_logical_tick": max_tick,
        "regions": regions,
        "transitions": transition_rows,
        "spatial_trails": spatial_trails,
    }
    projection_id = "ctp_" + sha256(_canonical(basis)).hexdigest()[:24]
    return {
        "schema": SCHEMA,
        "projection_id": projection_id,
        "world_id": world_id,
        "source": {
            "kind": "memoria.ia-v2-confirmed-nov-episodes",
            "snapshot_records": source_snapshot_records,
            "nov_observations": len(records),
            "checkpoint_cursor": checkpoint_cursor,
            "latest_logical_tick": max_tick,
            "spatial_observations": len(spatial_records),
        },
        "policy": {
            "visual_only": True,
            "world_write_authority": False,
            "selection_authority": False,
            "max_regions": MAX_REGIONS,
            "max_transitions": MAX_TRANSITIONS,
            "max_spatial_trails": MAX_SPATIAL_TRAILS,
            "episode_window_limit": MAX_RECORDS,
            "spatial_window_limit": MAX_SPATIAL_RECORDS,
            "height_cap_m": 18.0,
            "basin_cap_m": -12.0,
        },
        "regions": regions,
        "transitions": transition_rows,
        "spatial_trails": spatial_trails,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    encoded = _canonical(payload) + b"\n"
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise CognitiveTerrainError("projection_output_budget")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    if path.is_symlink():
        raise CognitiveTerrainError("projection_symlink")
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o640)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        folder = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if temp.exists():
            temp.unlink()


def project_once(
    *, db_path: Path = DEFAULT_DB, checkpoint_path: Path = DEFAULT_CHECKPOINT,
    world_path: Path = DEFAULT_WORLD, output_path: Path = DEFAULT_OUTPUT,
    spatial_index_path: Path = DEFAULT_SPATIAL_INDEX,
    spatial_db_path: Path = DEFAULT_SPATIAL_DB,
) -> dict[str, Any]:
    world_id, regions = _world_regions(world_path)
    checkpoint = _checkpoint(checkpoint_path, world_id)
    records, source_snapshot_records = _validated_rows(db_path, checkpoint, world_id)
    spatial_records = _validated_spatial_rows(spatial_index_path, spatial_db_path, world_id)
    projection = build_projection(
        world_id=world_id,
        known_regions=regions,
        records=records,
        source_snapshot_records=source_snapshot_records,
        checkpoint_cursor=int(checkpoint["cursor"]),
        spatial_records=spatial_records,
    )
    _atomic_write(output_path, projection)
    return {
        "status": "ok",
        "schema": SCHEMA,
        "projection_id": projection["projection_id"],
        "regions": len(projection["regions"]),
        "transitions": len(projection["transitions"]),
        "nov_observations": len(records),
        "spatial_observations": len(spatial_records),
        "spatial_trails": len(projection.get("spatial_trails", [])),
        "world_mutated": False,
        "selection_authority": False,
    }


class CognitiveTerrainProjectionReader:
    """Small cached reader for the runtime delivery side-channel."""

    def __init__(self, path: Path = DEFAULT_OUTPUT) -> None:
        self.path = path
        self._signature: tuple[int, int, int] | None = None
        self._cached: dict[str, Any] | None = None

    @staticmethod
    def _validate(value: dict[str, Any], world_id: str) -> None:
        policy = value.get("policy")
        regions = value.get("regions")
        transitions = value.get("transitions")
        spatial_trails = value.get("spatial_trails", [])
        if (
            value.get("schema") != SCHEMA
            or value.get("world_id") != world_id
            or not isinstance(value.get("projection_id"), str)
            or not isinstance(policy, dict)
            or policy.get("visual_only") is not True
            or policy.get("world_write_authority") is not False
            or policy.get("selection_authority") is not False
            or not isinstance(regions, list)
            or len(regions) > MAX_REGIONS
            or not isinstance(transitions, list)
            or len(transitions) > MAX_TRANSITIONS
            or not isinstance(spatial_trails, list)
            or len(spatial_trails) > MAX_SPATIAL_TRAILS
        ):
            raise CognitiveTerrainError("projection_contract")

    def read(self, world_id: str) -> dict[str, Any] | None:
        if self.path.is_symlink():
            raise CognitiveTerrainError("projection_symlink")
        try:
            info = self.path.stat()
        except FileNotFoundError:
            self._signature = None
            self._cached = None
            return None
        if not self.path.is_file() or info.st_size <= 0 or info.st_size > MAX_OUTPUT_BYTES:
            raise CognitiveTerrainError("projection_file_budget")
        signature = (info.st_ino, info.st_size, info.st_mtime_ns)
        if signature != self._signature:
            value = _read_json(self.path, MAX_OUTPUT_BYTES, "projection")
            self._validate(value, world_id)
            self._cached = value
            self._signature = signature
        if self._cached is not None and self._cached.get("world_id") != world_id:
            raise CognitiveTerrainError("projection_contract")
        return deepcopy(self._cached) if self._cached is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = project_once(
            db_path=args.db, checkpoint_path=args.checkpoint,
            world_path=args.world, output_path=args.output,
        )
    except (CognitiveTerrainError, OSError, sqlite3.Error, ValueError) as exc:
        raise SystemExit(f"COGNITIVE_TERRAIN_BLOCKED {type(exc).__name__}: {exc}") from exc
    print("COGNITIVE_TERRAIN_OK " + json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
