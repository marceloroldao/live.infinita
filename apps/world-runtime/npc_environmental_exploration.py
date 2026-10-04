"""008BY: local environmental stimulus for low-priority exploration.

The authoritative scheduler still chooses and authorizes motion. This adapter
reads the same stabilized terrain as presentation; memory has no write authority.
Regional climate is an approximation, not obstacle collision or drinking water.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from cognitive_terrain_projection import CognitiveTerrainError, CognitiveTerrainProjectionReader
from environmental_rules import EnvironmentalRulesError, derive_environmental_state, region_environment_map


def travel_discomfort(row: dict[str, Any]) -> float:
    def number(key: str, default: float = 0.0) -> float:
        try:
            value = float(row.get(key, default))
            return value if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default
    def unit(key: str) -> float:
        return max(0.0, min(1.0, number(key)))
    temp = number("current_temperature_c", 20.0)
    thermal = min(1.0, max(0.0, 8.0 - temp, temp - 30.0) / 20.0)
    slope = min(1.0, max(0.0, number("slope_deg")) / 35.0)
    # Wetland is a traversal cost, never proof of potable water or food.
    return round(
        0.30 * thermal + 0.24 * slope + 0.20 * unit("snow_cover")
        + 0.16 * unit("wetland_affinity") + 0.10 * unit("vegetation_density"), 6
    )


class EnvironmentalExploration:
    def __init__(self, world_provider: Callable[[], dict[str, Any]], projection_file: Path) -> None:
        self.world_provider = world_provider
        self.reader = CognitiveTerrainProjectionReader(projection_file)

    def __call__(self) -> dict[str, Any]:
        try:
            world = self.world_provider()
            projection = self.reader.read(str(world.get("world_id") or ""))
            if projection is None:
                return {}
            visual = dict(projection)
            if isinstance(projection.get("visual_regions"), list) and projection.get("visual_projection_id"):
                visual["regions"] = projection["visual_regions"]
                visual["projection_id"] = projection["visual_projection_id"]
            state = derive_environmental_state(world, visual)
            return {"state_id": state["state_id"], "regions": region_environment_map(state)}
        except (CognitiveTerrainError, EnvironmentalRulesError, OSError, ValueError):
            # Missing/rejected evidence preserves the original exploration policy.
            return {}


def choose_local_region(
    choices: list[str], baseline: str, stimulus: dict[str, Any], bucket: int
) -> tuple[str, dict[str, Any]]:
    rows = stimulus.get("regions") or {}
    # Every fourth crossing remains baseline exploration, avoiding permanent
    # exclusion of uncomfortable regions. Missing evidence never means safety.
    if not isinstance(rows, dict) or any(not isinstance(rows.get(key), dict) for key in choices):
        return baseline, {"mode": "topology_fallback"}
    scores = {key: travel_discomfort(rows[key]) for key in choices}
    best = min(choices, key=lambda key: (scores[key], choices.index(key)))
    target = baseline
    mode = "exploration" if (bucket // 4) % 4 == 0 else "baseline"
    if mode == "exploration":
        target = choices[((bucket // 4) // 4) % len(choices)]
    elif scores[baseline] - scores[best] >= 0.12:
        target, mode = best, "environment_preference"
    return target, {
        "mode": mode, "environment_state_id": stimulus.get("state_id"),
        "candidate_region_ids": list(choices), "travel_discomfort": scores,
        "selected_region_id": target,
    }
