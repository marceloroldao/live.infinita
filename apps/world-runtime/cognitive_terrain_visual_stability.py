from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

SCHEMA = "live-infinita-cognitive-visual-stability/v1"

REGION_ELEVATION_STEP_M = 0.65
REGION_RADIUS_STEP_M = 3.0
REGION_MASS_STEP = 0.03
RIDGE_HEIGHT_STEP_M = 0.65
RIDGE_WIDTH_STEP_M = 3.0
RELATION_STRENGTH_STEP = 0.05
RELATION_COUNT_STEP = 2
TRAIL_STRENGTH_STEP = 0.08
TRAIL_WIDTH_STEP_M = 0.15

LAKE_APPEAR_ELEVATION_M = -6.5
LAKE_DISAPPEAR_ELEVATION_M = -4.5
ROLE_SETTLE_ELEVATION_M = 1.3
ROLE_SETTLE_MASS = 0.08

VISUAL_REFRESH_HINT_SECONDS = 120
MAX_VISUAL_REGIONS = 32
MAX_VISUAL_TRANSITIONS = 48
MAX_VISUAL_SPATIAL_TRAILS = 128


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _approach(current: float, target: float, step: float) -> float:
    current = float(current)
    target = float(target)
    step = max(0.0, float(step))
    if current < target:
        return min(target, current + step)
    if current > target:
        return max(target, current - step)
    return current


def _region_map(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("region_id") or ""): row
        for row in rows
        if isinstance(row, dict) and str(row.get("region_id") or "")
    }


def _edge_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("from_region_id") or ""),
        str(row.get("to_region_id") or ""),
    )


def _edge_map(rows: Any) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        _edge_key(row): row
        for row in rows
        if isinstance(row, dict) and all(_edge_key(row))
    }


def _position_key(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        return (
            round(float(value.get("x", 0.0)), 3),
            round(float(value.get("y", value.get("z", 0.0))), 3),
        )
    except (TypeError, ValueError):
        return None


def _spatial_key(row: dict[str, Any]) -> tuple[Any, ...] | None:
    source = _position_key(row.get("from_position"))
    target = _position_key(row.get("to_position"))
    if source is None or target is None:
        return None
    return (
        source,
        target,
        str(row.get("from_region_id") or ""),
        str(row.get("to_region_id") or ""),
    )


def _spatial_map(rows: Any) -> dict[tuple[Any, ...], dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _spatial_key(row)
        if key is not None:
            result[key] = row
    return result




def _compact_region(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "region_id": row.get("region_id"),
        "center": deepcopy(row.get("center")),
        "elevation_bias_m": row.get("elevation_bias_m"),
        "influence_radius_m": row.get("influence_radius_m"),
        "cognitive_mass": row.get("cognitive_mass"),
        "terrain_role": row.get("terrain_role"),
        "lake_candidate": row.get("lake_candidate"),
    }


def _compact_transition(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_region_id": row.get("from_region_id"),
        "to_region_id": row.get("to_region_id"),
        "count": row.get("count", 0),
        "strength": row.get("strength", 0.0),
        "ridge_height_m": row.get("ridge_height_m", 0.0),
        "ridge_width_m": row.get("ridge_width_m", 28.0),
        "trail_strength": row.get("trail_strength", 0.0),
        "trail_width_m": row.get("trail_width_m", 0.7),
        "trail_candidate": row.get("trail_candidate", False),
    }


def _compact_spatial(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_position": deepcopy(row.get("from_position")),
        "to_position": deepcopy(row.get("to_position")),
        "from_region_id": row.get("from_region_id"),
        "to_region_id": row.get("to_region_id"),
        "count": row.get("count", 0),
        "trail_strength": row.get("trail_strength", 0.0),
        "trail_width_m": row.get("trail_width_m", 0.6),
        "trail_candidate": row.get("trail_candidate", False),
    }

def _decay_visual_region(
    previous: dict[str, Any],
) -> dict[str, Any] | None:
    out = _compact_region(previous)
    elevation = _approach(
        float(previous.get("elevation_bias_m", 0.0)),
        0.0,
        REGION_ELEVATION_STEP_M,
    )
    radius = _approach(
        float(previous.get("influence_radius_m", 115.0)),
        115.0,
        REGION_RADIUS_STEP_M,
    )
    mass = _approach(
        float(previous.get("cognitive_mass", 0.0)),
        0.0,
        REGION_MASS_STEP,
    )
    lake = bool(previous.get("lake_candidate", False))
    if lake and elevation >= LAKE_DISAPPEAR_ELEVATION_M:
        lake = False

    role = str(previous.get("terrain_role") or "memory_field")
    if (
        abs(elevation) <= ROLE_SETTLE_ELEVATION_M
        and mass <= ROLE_SETTLE_MASS
    ):
        role = "memory_field"

    if (
        abs(elevation) <= 0.05
        and abs(radius - 115.0) <= 0.05
        and mass <= 0.005
        and not lake
        and role == "memory_field"
    ):
        return None

    out["elevation_bias_m"] = round(elevation, 4)
    out["influence_radius_m"] = round(radius, 3)
    out["cognitive_mass"] = round(mass, 6)
    out["terrain_role"] = role
    out["lake_candidate"] = lake
    return out


def _visual_region(
    raw: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    out = _compact_region(raw)
    if previous is None:
        current_elevation = 0.0
        current_radius = 115.0
        current_mass = 0.0
        current_role = "memory_field"
        current_lake = False
    else:
        current_elevation = float(previous.get("elevation_bias_m", 0.0))
        current_radius = float(previous.get("influence_radius_m", 115.0))
        current_mass = float(previous.get("cognitive_mass", 0.0))
        current_role = str(previous.get("terrain_role") or "memory_field")
        current_lake = bool(previous.get("lake_candidate", False))

    target_elevation = float(raw.get("elevation_bias_m", 0.0))
    target_radius = float(raw.get("influence_radius_m", 115.0))
    target_mass = float(raw.get("cognitive_mass", 0.0))

    elevation = _approach(
        current_elevation,
        target_elevation,
        REGION_ELEVATION_STEP_M,
    )
    radius = _approach(
        current_radius,
        target_radius,
        REGION_RADIUS_STEP_M,
    )
    mass = _approach(
        current_mass,
        target_mass,
        REGION_MASS_STEP,
    )

    target_role = str(raw.get("terrain_role") or "memory_field")
    role = current_role
    if target_role == current_role:
        role = target_role
    elif (
        abs(elevation - target_elevation) <= ROLE_SETTLE_ELEVATION_M
        and abs(mass - target_mass) <= ROLE_SETTLE_MASS
    ):
        role = target_role

    target_lake = bool(raw.get("lake_candidate", False))
    lake = current_lake
    if not current_lake and target_lake and elevation <= LAKE_APPEAR_ELEVATION_M:
        lake = True
    elif (
        current_lake
        and not target_lake
        and (
            elevation >= LAKE_DISAPPEAR_ELEVATION_M
            or abs(elevation - target_elevation) <= ROLE_SETTLE_ELEVATION_M
        )
    ):
        lake = False

    out["elevation_bias_m"] = round(elevation, 4)
    out["influence_radius_m"] = round(radius, 3)
    out["cognitive_mass"] = round(mass, 6)
    out["terrain_role"] = role
    out["lake_candidate"] = lake
    return out


def _visual_transition(
    raw: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if raw is None and previous is None:
        return None
    source = raw if raw is not None else previous
    assert isinstance(source, dict)
    base = _compact_transition(source)

    if previous is None:
        current_height = 0.0
        current_width = 28.0
        current_relation_strength = 0.0
        current_count = 0
        current_strength = 0.0
        current_trail_width = 0.7
        current_candidate = False
    else:
        current_height = float(previous.get("ridge_height_m", 0.0))
        current_width = float(previous.get("ridge_width_m", 28.0))
        current_relation_strength = float(previous.get("strength", 0.0))
        current_count = int(previous.get("count", 0))
        current_strength = float(previous.get("trail_strength", 0.0))
        current_trail_width = float(previous.get("trail_width_m", 0.7))
        current_candidate = bool(previous.get("trail_candidate", False))

    target_height = float(raw.get("ridge_height_m", 0.0)) if raw is not None else 0.0
    target_width = float(raw.get("ridge_width_m", 28.0)) if raw is not None else 28.0
    target_relation_strength = float(raw.get("strength", 0.0)) if raw is not None else 0.0
    target_count = int(raw.get("count", 0)) if raw is not None else 0
    target_strength = float(raw.get("trail_strength", 0.0)) if raw is not None else 0.0
    target_trail_width = float(raw.get("trail_width_m", 0.7)) if raw is not None else 0.7
    target_candidate = bool(raw.get("trail_candidate", False)) if raw is not None else False

    height = _approach(current_height, target_height, RIDGE_HEIGHT_STEP_M)
    width = _approach(current_width, target_width, RIDGE_WIDTH_STEP_M)
    relation_strength = _approach(
        current_relation_strength,
        target_relation_strength,
        RELATION_STRENGTH_STEP,
    )
    count = int(round(_approach(current_count, target_count, RELATION_COUNT_STEP)))
    strength = _approach(current_strength, target_strength, TRAIL_STRENGTH_STEP)
    trail_width = _approach(current_trail_width, target_trail_width, TRAIL_WIDTH_STEP_M)

    candidate = current_candidate
    if not current_candidate and target_candidate and strength >= 0.28:
        candidate = True
    elif current_candidate and not target_candidate and strength <= 0.12:
        candidate = False

    if (
        raw is None
        and height <= 0.05
        and relation_strength <= 0.02
        and count <= 0
        and strength <= 0.02
        and not candidate
    ):
        return None

    base["count"] = count
    base["strength"] = round(relation_strength, 6)
    base["ridge_height_m"] = round(height, 4)
    base["ridge_width_m"] = round(width, 3)
    base["trail_strength"] = round(strength, 6)
    base["trail_width_m"] = round(trail_width, 3)
    base["trail_candidate"] = candidate
    return base


def _visual_spatial_trail(
    raw: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if raw is None and previous is None:
        return None
    source = raw if raw is not None else previous
    assert isinstance(source, dict)
    base = _compact_spatial(source)

    if previous is None:
        current_count = 0
        current_strength = 0.0
        current_width = 0.6
        current_candidate = False
    else:
        current_count = int(previous.get("count", 0))
        current_strength = float(previous.get("trail_strength", 0.0))
        current_width = float(previous.get("trail_width_m", 0.6))
        current_candidate = bool(previous.get("trail_candidate", False))

    target_count = int(raw.get("count", 0)) if raw is not None else 0
    target_strength = float(raw.get("trail_strength", 0.0)) if raw is not None else 0.0
    target_width = float(raw.get("trail_width_m", 0.6)) if raw is not None else 0.6
    target_candidate = bool(raw.get("trail_candidate", False)) if raw is not None else False

    count = int(round(_approach(current_count, target_count, RELATION_COUNT_STEP)))
    strength = _approach(current_strength, target_strength, TRAIL_STRENGTH_STEP)
    width = _approach(current_width, target_width, TRAIL_WIDTH_STEP_M)

    candidate = current_candidate
    if not current_candidate and target_candidate and strength >= 0.28:
        candidate = True
    elif current_candidate and not target_candidate and strength <= 0.10:
        candidate = False

    if raw is None and count <= 0 and strength <= 0.02 and not candidate:
        return None

    base["count"] = count
    base["trail_strength"] = round(strength, 6)
    base["trail_width_m"] = round(width, 3)
    base["trail_candidate"] = candidate
    return base


def _visual_basis(
    world_id: str,
    regions: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    spatial_trails: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "world_id": world_id,
        "regions": [
            {
                "region_id": row.get("region_id"),
                "elevation_bias_m": row.get("elevation_bias_m"),
                "influence_radius_m": row.get("influence_radius_m"),
                "cognitive_mass": row.get("cognitive_mass"),
                "terrain_role": row.get("terrain_role"),
                "lake_candidate": row.get("lake_candidate"),
            }
            for row in regions
        ],
        "transitions": [
            {
                "from_region_id": row.get("from_region_id"),
                "to_region_id": row.get("to_region_id"),
                "count": row.get("count"),
                "strength": row.get("strength"),
                "ridge_height_m": row.get("ridge_height_m"),
                "ridge_width_m": row.get("ridge_width_m"),
                "trail_strength": row.get("trail_strength"),
                "trail_width_m": row.get("trail_width_m"),
                "trail_candidate": row.get("trail_candidate"),
            }
            for row in transitions
        ],
        "spatial_trails": [
            {
                "from_position": row.get("from_position"),
                "to_position": row.get("to_position"),
                "from_region_id": row.get("from_region_id"),
                "to_region_id": row.get("to_region_id"),
                "count": row.get("count"),
                "trail_strength": row.get("trail_strength"),
                "trail_width_m": row.get("trail_width_m"),
                "trail_candidate": row.get("trail_candidate"),
            }
            for row in spatial_trails
        ],
    }


def stabilize_visual_projection(
    projection: dict[str, Any],
    previous_projection: dict[str, Any] | None,
) -> dict[str, Any]:
    result = deepcopy(projection)
    world_id = str(projection.get("world_id") or "")

    previous_valid = (
        isinstance(previous_projection, dict)
        and previous_projection.get("schema") == projection.get("schema")
        and str(previous_projection.get("world_id") or "") == world_id
        and isinstance(previous_projection.get("visual_regions"), list)
        and isinstance(previous_projection.get("visual_transitions"), list)
        and isinstance(previous_projection.get("visual_spatial_trails"), list)
        and isinstance(previous_projection.get("visual_projection_id"), str)
    )

    raw_regions = list(projection.get("regions") or [])
    raw_transitions = list(projection.get("transitions") or [])
    raw_spatial = list(projection.get("spatial_trails") or [])

    target_regions = [
        _compact_region(row) for row in raw_regions if isinstance(row, dict)
    ]
    target_regions.sort(key=lambda row: str(row.get("region_id") or ""))
    target_regions = target_regions[:MAX_VISUAL_REGIONS]

    target_transitions = [
        _compact_transition(row)
        for row in raw_transitions
        if isinstance(row, dict)
    ]
    target_transitions.sort(key=_edge_key)
    target_transitions = target_transitions[:MAX_VISUAL_TRANSITIONS]

    target_spatial = [
        _compact_spatial(row) for row in raw_spatial if isinstance(row, dict)
    ]
    target_spatial.sort(key=lambda row: repr(_spatial_key(row)))
    target_spatial = target_spatial[:MAX_VISUAL_SPATIAL_TRAILS]

    target_visual_id = "vctp_" + sha256(
        _canonical(
            _visual_basis(
                world_id,
                target_regions,
                target_transitions,
                target_spatial,
            )
        )
    ).hexdigest()[:24]

    if (
        previous_valid
        and previous_projection is not None
        and str(previous_projection.get("projection_id") or "")
        == str(projection.get("projection_id") or "")
        and str(previous_projection.get("visual_projection_id") or "")
        == target_visual_id
    ):
        result["visual_projection_id"] = previous_projection["visual_projection_id"]
        result["visual_regions"] = deepcopy(previous_projection["visual_regions"])
        result["visual_transitions"] = deepcopy(
            previous_projection["visual_transitions"]
        )
        result["visual_spatial_trails"] = deepcopy(
            previous_projection["visual_spatial_trails"]
        )
        result["visual_stability"] = deepcopy(
            previous_projection.get("visual_stability", {})
        )
        return result

    if not previous_valid:
        visual_regions = deepcopy(target_regions)
        visual_transitions = deepcopy(target_transitions)
        visual_spatial = deepcopy(target_spatial)
        bootstrap = True
        previous_visual_id = ""
    else:
        assert previous_projection is not None
        bootstrap = False
        previous_visual_id = str(previous_projection.get("visual_projection_id") or "")

        prev_regions = _region_map(previous_projection.get("visual_regions"))
        raw_region_map = _region_map(raw_regions)
        visual_regions = []
        for region_id in sorted(set(raw_region_map) | set(prev_regions)):
            raw_region = raw_region_map.get(region_id)
            if raw_region is not None:
                visual_regions.append(
                    _visual_region(raw_region, prev_regions.get(region_id))
                )
            else:
                decayed = _decay_visual_region(prev_regions[region_id])
                if decayed is not None:
                    visual_regions.append(decayed)

        raw_edges = _edge_map(raw_transitions)
        prev_edges = _edge_map(previous_projection.get("visual_transitions"))
        visual_transitions = []
        for key in sorted(set(raw_edges) | set(prev_edges)):
            row = _visual_transition(raw_edges.get(key), prev_edges.get(key))
            if row is not None:
                visual_transitions.append(row)

        raw_spatial_map = _spatial_map(raw_spatial)
        prev_spatial_map = _spatial_map(previous_projection.get("visual_spatial_trails"))
        visual_spatial = []
        for key in sorted(set(raw_spatial_map) | set(prev_spatial_map), key=repr):
            row = _visual_spatial_trail(
                raw_spatial_map.get(key),
                prev_spatial_map.get(key),
            )
            if row is not None:
                visual_spatial.append(row)

    visual_regions.sort(key=lambda row: str(row.get("region_id") or ""))
    visual_regions = visual_regions[:MAX_VISUAL_REGIONS]

    visual_transitions.sort(
        key=lambda row: (
            -float(row.get("ridge_height_m", 0.0)),
            -float(row.get("trail_strength", 0.0)),
            _edge_key(row),
        )
    )
    visual_transitions = visual_transitions[:MAX_VISUAL_TRANSITIONS]
    visual_transitions.sort(key=_edge_key)

    visual_spatial.sort(
        key=lambda row: (
            -float(row.get("trail_strength", 0.0)),
            repr(_spatial_key(row)),
        )
    )
    visual_spatial = visual_spatial[:MAX_VISUAL_SPATIAL_TRAILS]
    visual_spatial.sort(key=lambda row: repr(_spatial_key(row)))

    basis = _visual_basis(
        world_id,
        visual_regions,
        visual_transitions,
        visual_spatial,
    )
    visual_projection_id = "vctp_" + sha256(_canonical(basis)).hexdigest()[:24]

    result["visual_projection_id"] = visual_projection_id
    result["visual_regions"] = visual_regions
    result["visual_transitions"] = visual_transitions
    result["visual_spatial_trails"] = visual_spatial
    result["visual_stability"] = {
        "schema": SCHEMA,
        "source_projection_id": str(projection.get("projection_id") or ""),
        "previous_visual_projection_id": previous_visual_id,
        "bootstrap": bootstrap,
        "refresh_hint_seconds": VISUAL_REFRESH_HINT_SECONDS,
        "rates": {
            "region_elevation_step_m": REGION_ELEVATION_STEP_M,
            "region_radius_step_m": REGION_RADIUS_STEP_M,
            "region_mass_step": REGION_MASS_STEP,
            "ridge_height_step_m": RIDGE_HEIGHT_STEP_M,
            "ridge_width_step_m": RIDGE_WIDTH_STEP_M,
            "relation_strength_step": RELATION_STRENGTH_STEP,
            "relation_count_step": RELATION_COUNT_STEP,
            "trail_strength_step": TRAIL_STRENGTH_STEP,
            "trail_width_step_m": TRAIL_WIDTH_STEP_M,
        },
        "hysteresis": {
            "lake_appear_elevation_m": LAKE_APPEAR_ELEVATION_M,
            "lake_disappear_elevation_m": LAKE_DISAPPEAR_ELEVATION_M,
        },
        "policy": {
            "raw_projection_remains_authoritative": True,
            "visual_fields_are_presentation_only": True,
        },
    }
    return result
