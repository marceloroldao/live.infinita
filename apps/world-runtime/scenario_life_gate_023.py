from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_022 import build_life_gate_022_world


def build_life_gate_023_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Passive-forgetting world: a formerly admitted proxy disappears entirely."""
    world = deepcopy(
        build_life_gate_022_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-023-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["higher_order_context_selector"][
        "forgetting_lambda0"
    ] = 0.025
    world["rules"]["higher_order_context_selector"][
        "forgetting_consolidation"
    ] = 1.0
    world["rules"]["higher_order_passive_forgetting"] = {
        "proxy_sensor_id": "s_regime_proxy_01",
        "proxy_band_id": "x0",
        "phase_1_proxy_context_phase": "b_clear",
        "phase_2_proxy_present": False,
        "observations_per_combination": 5,
        "slice_time_step": 1.0,
    }
    return world


def initial_nov_needs_023(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
