from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_020 import build_life_gate_020_world


def build_life_gate_021_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Stress evidence selection with recurrent temporally-local distractors."""
    world = deepcopy(
        build_life_gate_020_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-021-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["higher_order_stress"] = {
        "recurring_close_distractors": 8,
    }
    return world


def initial_nov_needs_021(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
