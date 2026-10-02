"""008BE: deterministic environmental rules derived from world cognition.

Cognitive terrain is a stimulus, never environmental authority and never a
World State writer. The rules below turn the compressed visual/cognitive
topography into an environmental state that agents and renderers may consult.

The visual world compresses vertical scale heavily. VERTICAL_SCALE maps one
meter of cognitive/visual elevation bias to an effective environmental altitude
used only by this model. It does not rewrite geometry or claim geographic scale.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from typing import Any

SCHEMA = "live-infinita-environmental-state/v1"
VERTICAL_SCALE = 180.0
DEFAULT_BASE_ALTITUDE_M = 180.0
DEFAULT_BASE_TEMPERATURE_C = 22.0
DEFAULT_ANNUAL_PRECIPITATION_MM = 1400.0
TEMPERATURE_LAPSE_C_PER_KM = 6.5
WATERLIKE_BIOMES = frozenset({"river", "waterfall"})

_WEATHER_TEMP_OFFSET = {
    "clear": 0.0,
    "cloudy": -0.8,
    "rain": -1.5,
    "storm": -2.0,
    "snow": -4.0,
}
_WEATHER_MOISTURE_OFFSET = {
    "clear": -0.02,
    "cloudy": 0.02,
    "rain": 0.12,
    "storm": 0.18,
    "snow": 0.08,
}


class EnvironmentalRulesError(ValueError):
    pass


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _number(value: object, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if math.isfinite(result) else float(default)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _world_regions(world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = world.get("regions")
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        region_id = str(raw.get("id") or "").strip()
        if not region_id:
            continue
        result[region_id] = {
            "biome": str(raw.get("biome") or "unknown"),
            "radius": max(1.0, _number(raw.get("radius"), 100.0)),
        }
    return result


def _climate(world: dict[str, Any]) -> dict[str, float | str]:
    environment = world.get("environment")
    environment = environment if isinstance(environment, dict) else {}
    climate = environment.get("climate")
    climate = climate if isinstance(climate, dict) else {}
    weather = str(environment.get("weather") or "clear").strip().lower() or "clear"
    period = str(environment.get("period") or "day").strip().lower() or "day"
    atmosphere = _clamp(_number(environment.get("atmosphere_intensity"), 0.58), 0.0, 1.0)
    return {
        "base_altitude_m": _clamp(
            _number(climate.get("base_altitude_m"), DEFAULT_BASE_ALTITUDE_M), 0.0, 2500.0
        ),
        "base_temperature_c": _clamp(
            _number(climate.get("base_temperature_c"), DEFAULT_BASE_TEMPERATURE_C),
            -10.0,
            38.0,
        ),
        "annual_precipitation_mm": _clamp(
            _number(
                climate.get("annual_precipitation_mm"),
                DEFAULT_ANNUAL_PRECIPITATION_MM,
            ),
            100.0,
            5000.0,
        ),
        "seasonal_temperature_offset_c": _clamp(
            _number(climate.get("seasonal_temperature_offset_c"), 0.0), -15.0, 15.0
        ),
        "weather": weather,
        "period": period,
        "atmosphere_intensity": atmosphere,
    }


def _slope_degrees(elevation_bias_m: float, influence_radius_m: float) -> float:
    run = max(8.0, influence_radius_m * 0.35)
    return math.degrees(math.atan2(abs(elevation_bias_m), run))


def _temperature_suitability(temp_c: float) -> float:
    if temp_c <= -5.0 or temp_c >= 38.0:
        return 0.0
    if 10.0 <= temp_c <= 28.0:
        return 1.0
    if temp_c < 10.0:
        return _clamp((temp_c + 5.0) / 15.0, 0.0, 1.0)
    return _clamp((38.0 - temp_c) / 10.0, 0.0, 1.0)


def _tree_temperature_suitability(temp_c: float) -> float:
    if temp_c <= 2.0 or temp_c >= 35.0:
        return 0.0
    if 9.0 <= temp_c <= 27.0:
        return 1.0
    if temp_c < 9.0:
        return _clamp((temp_c - 2.0) / 7.0, 0.0, 1.0)
    return _clamp((35.0 - temp_c) / 8.0, 0.0, 1.0)


def _ecological_zone(
    *,
    effective_altitude_m: float,
    climate_temperature_c: float,
    soil_moisture: float,
    snow_cover: float,
    rock_exposure: float,
    vegetation_density: float,
    tree_suitability: float,
    water_influence: float,
) -> str:
    if snow_cover >= 0.55:
        return "snowfield"
    if effective_altitude_m >= 2400.0 and rock_exposure >= 0.45:
        return "alpine_rock"
    if effective_altitude_m >= 1800.0 or climate_temperature_c < 8.0:
        return "alpine_meadow" if vegetation_density >= 0.18 else "alpine_rock"
    if water_influence >= 0.7 and soil_moisture >= 0.78:
        return "wetland"
    if tree_suitability >= 0.62:
        return "forest"
    if vegetation_density >= 0.48:
        return "meadow"
    if vegetation_density >= 0.22:
        return "shrubland"
    return "sparse"


def _climate_type(temp_c: float, precipitation_mm: float, altitude_m: float) -> str:
    if altitude_m >= 2400.0 or temp_c < 5.0:
        return "alpine_cold"
    if altitude_m >= 1200.0 or temp_c < 12.0:
        return "cool_montane"
    if precipitation_mm < 650.0:
        return "temperate_dry"
    if temp_c >= 24.0:
        return "warm_humid"
    return "temperate_humid"


def derive_environmental_state(
    world: dict[str, Any],
    cognitive_projection: dict[str, Any],
) -> dict[str, Any]:
    """Return a bounded read-only environmental state for every projected region."""
    if not isinstance(world, dict) or not isinstance(cognitive_projection, dict):
        raise EnvironmentalRulesError("environmental_input_invalid")
    world_id = str(world.get("world_id") or "").strip()
    projection_world_id = str(cognitive_projection.get("world_id") or "").strip()
    if not world_id or projection_world_id != world_id:
        raise EnvironmentalRulesError("environmental_world_mismatch")

    rows = cognitive_projection.get("regions")
    if not isinstance(rows, list):
        raise EnvironmentalRulesError("environmental_projection_regions_invalid")

    climate = _climate(world)
    regions = _world_regions(world)
    output_rows: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        region_id = str(raw.get("region_id") or "").strip()
        canonical_region = regions.get(region_id)
        if canonical_region is None:
            continue

        bias = _clamp(_number(raw.get("elevation_bias_m"), 0.0), -12.0, 18.0)
        influence = _clamp(_number(raw.get("influence_radius_m"), 115.0), 40.0, 260.0)
        mass = _clamp(_number(raw.get("cognitive_mass"), 0.0), 0.0, 1.0)
        role = str(raw.get("terrain_role") or "memory_field")
        lake_candidate = bool(raw.get("lake_candidate", False))
        biome = str(canonical_region.get("biome") or "unknown").lower()

        effective_altitude = _clamp(
            float(climate["base_altitude_m"]) + max(-1.0, bias) * VERTICAL_SCALE,
            0.0,
            4200.0,
        )
        climate_temp = (
            float(climate["base_temperature_c"])
            + float(climate["seasonal_temperature_offset_c"])
            - TEMPERATURE_LAPSE_C_PER_KM * (effective_altitude / 1000.0)
        )
        current_temp = climate_temp + _WEATHER_TEMP_OFFSET.get(str(climate["weather"]), 0.0)
        if str(climate["period"]) == "night":
            current_temp -= 1.8

        slope_deg = _slope_degrees(bias, influence)
        slope_drain = _clamp(slope_deg / 38.0, 0.0, 1.0)
        precipitation_norm = _clamp(
            float(climate["annual_precipitation_mm"]) / 1800.0, 0.08, 1.0
        )
        water_influence = 1.0 if biome in WATERLIKE_BIOMES else 0.0
        if lake_candidate:
            water_influence = max(water_influence, 0.95)
        elif role == "basin":
            water_influence = max(water_influence, 0.55)

        soil_moisture = _clamp(
            0.12
            + 0.62 * precipitation_norm
            + 0.28 * water_influence
            - 0.24 * slope_drain
            + _WEATHER_MOISTURE_OFFSET.get(str(climate["weather"]), 0.0),
            0.0,
            1.0,
        )

        snow_thermal = _clamp((3.0 - climate_temp) / 11.0, 0.0, 1.0)
        snow_cover = _clamp(
            snow_thermal * (0.45 + 0.55 * precipitation_norm), 0.0, 1.0
        )
        altitude_rock = _clamp((effective_altitude - 1500.0) / 1800.0, 0.0, 1.0)
        slope_rock = _clamp((slope_deg - 12.0) / 28.0, 0.0, 1.0)
        rock_exposure = _clamp(
            0.08 + 0.56 * altitude_rock + 0.34 * slope_rock + 0.18 * snow_cover,
            0.0,
            1.0,
        )

        vegetation_density = _clamp(
            soil_moisture
            * _temperature_suitability(climate_temp)
            * (1.0 - 0.72 * rock_exposure)
            * (1.0 - 0.78 * snow_cover),
            0.0,
            1.0,
        )
        tree_suitability = _clamp(
            soil_moisture
            * _tree_temperature_suitability(climate_temp)
            * (1.0 - rock_exposure)
            * (1.0 - snow_cover)
            * (1.0 - 0.75 * slope_drain),
            0.0,
            1.0,
        )

        zone = _ecological_zone(
            effective_altitude_m=effective_altitude,
            climate_temperature_c=climate_temp,
            soil_moisture=soil_moisture,
            snow_cover=snow_cover,
            rock_exposure=rock_exposure,
            vegetation_density=vegetation_density,
            tree_suitability=tree_suitability,
            water_influence=water_influence,
        )
        output_rows.append({
            "region_id": region_id,
            "source_biome": biome,
            "cognitive_mass": round(mass, 6),
            "terrain_role": role,
            "effective_altitude_m": round(effective_altitude, 2),
            "slope_deg": round(slope_deg, 3),
            "climate_type": _climate_type(
                climate_temp,
                float(climate["annual_precipitation_mm"]),
                effective_altitude,
            ),
            "climate_temperature_c": round(climate_temp, 2),
            "current_temperature_c": round(current_temp, 2),
            "annual_precipitation_mm": round(float(climate["annual_precipitation_mm"]), 1),
            "soil_moisture": round(soil_moisture, 4),
            "water_influence": round(water_influence, 4),
            "snow_cover": round(snow_cover, 4),
            "rock_exposure": round(rock_exposure, 4),
            "vegetation_density": round(vegetation_density, 4),
            "tree_suitability": round(tree_suitability, 4),
            "trees_allowed": tree_suitability >= 0.42,
            "ecological_zone": zone,
        })

    output_rows.sort(key=lambda row: row["region_id"])
    state_core = {
        "world_id": world_id,
        "source_projection_id": str(cognitive_projection.get("projection_id") or ""),
        "climate": climate,
        "regions": output_rows,
    }
    state_id = "env_" + sha256(_canonical(state_core)).hexdigest()[:24]
    return {
        "schema": SCHEMA,
        "state_id": state_id,
        **deepcopy(state_core),
        "policy": {
            "derived_from_cognition": True,
            "memory_is_authority": False,
            "world_write_authority": False,
            "selection_authority": False,
            "visual_vertical_scale": VERTICAL_SCALE,
        },
    }


def region_environment_map(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("regions") if isinstance(state, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(row["region_id"]): row
        for row in rows
        if isinstance(row, dict) and str(row.get("region_id") or "").strip()
    }
