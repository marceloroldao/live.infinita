from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_025 import build_life_gate_025_world


def build_life_gate_026_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Gradual remapping world with an explicit ambiguous transition window."""
    world = deepcopy(
        build_life_gate_025_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-026-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["higher_order_gradual_remap"] = {
        "proxy_sensor_id": "s_regime_proxy_01",
        "proxy_band_id": "x0",
        "initial_context_phase": "b_clear",
        "new_context_phase": "b_blocked",
        "initial_rounds": 5,
        "transition_rounds": 4,
        "active_evidence_slice_window": 20,
    }
    return world


def initial_nov_needs_026(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
