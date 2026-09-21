from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_019 import build_life_gate_019_world


def build_life_gate_020_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Stress sparse higher-order indexing with distractor-rich RealitySlices."""
    world = deepcopy(
        build_life_gate_019_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-020-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["higher_order_context_selector"]["min_pattern_support"] = 2
    world["rules"]["higher_order_stress"] = {
        "one_shot_distractors": 48,
        "recurring_distractors": 8,
    }
    return world


def initial_nov_needs_020(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
