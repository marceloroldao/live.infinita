from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_024 import build_life_gate_024_world


def build_life_gate_025_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Post-forgetting remap: the same proxy context returns with a new consequence."""
    world = deepcopy(
        build_life_gate_024_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-025-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["higher_order_context_selector"][
        "active_evidence_slice_window"
    ] = 20
    world["rules"]["higher_order_remapping"] = {
        "proxy_sensor_id": "s_regime_proxy_01",
        "proxy_band_id": "x0",
        "phase_1_proxy_context_phase": "b_clear",
        "phase_2_proxy_present": False,
        "phase_3_proxy_context_phase": "b_blocked",
        "observations_per_combination": 5,
        "active_evidence_slice_window": 20,
    }
    return world


def initial_nov_needs_025(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
