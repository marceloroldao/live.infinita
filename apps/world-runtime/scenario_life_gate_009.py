from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_008 import build_life_gate_008_world


def build_life_gate_009_world(*, episode_id: int = 0) -> dict:
    """Add a world-owned admission policy for presemantic temporal evidence."""
    world = deepcopy(build_life_gate_008_world(episode_id=episode_id))
    world["world_id"] = f"life-gate-009-episode-{episode_id}"
    world["rules"]["temporal_evidence_selector"] = {
        "min_repetitions": 3,
        "min_independent_slices": 3,
        "min_rho": 0.39,
        "min_selectivity": 0.80,
        "min_temporal_stability": 0.90,
        "min_evidence_score": 3.0,
        "min_direction_confidence": 0.80,
    }
    return world


def initial_nov_needs_009(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
