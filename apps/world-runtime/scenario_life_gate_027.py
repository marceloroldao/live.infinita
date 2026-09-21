from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_026 import build_life_gate_026_world


def build_life_gate_027_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Event-rate stress for current higher-order evidence windows."""
    world = deepcopy(
        build_life_gate_026_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-027-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    selector = world["rules"]["higher_order_context_selector"]
    selector["active_evidence_slice_window"] = 0
    selector["active_evidence_time_window"] = 25.0
    selector["forgetting_lambda0"] = 0.0

    world["rules"]["higher_order_event_rate_stress"] = {
        "relevant_rounds": 5,
        "count_window": 20,
        "time_window": 25.0,
        "slow_noise_slices": 2,
        "fast_noise_slices": 100,
        "noise_physical_span": 1.0,
    }
    return world


def initial_nov_needs_027(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
