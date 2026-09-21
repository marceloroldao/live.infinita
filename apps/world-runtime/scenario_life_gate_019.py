from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_018 import build_life_gate_018_world


def build_life_gate_019_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Enable sparse higher-order structural evidence over the Gate 018 XOR world."""
    world = deepcopy(
        build_life_gate_018_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-019-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["higher_order_context_selector"] = {
        "min_repetitions": 3,
        "min_independent_slices": 3,
        "min_rho": 0.39,
        "min_context_reliability": 0.75,
        "max_lower_order_reliability": 0.75,
        "context_span": 0.15,
        "max_consequence_delay": 1.5,
    }
    return world


def initial_nov_needs_019(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
