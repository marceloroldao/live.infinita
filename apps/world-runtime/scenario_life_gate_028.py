from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_027 import build_life_gate_027_world


def build_life_gate_028_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Event-time vs arrival-order stress with bounded lateness."""
    world = deepcopy(
        build_life_gate_027_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
            barrier_phase_id=barrier_phase_id,
        )
    )
    world["world_id"] = (
        f"life-gate-028-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )
    world["rules"]["reality_slice_event_time"] = {
        "allowed_lateness": 4.0,
        "late_policy": "reject-audit",
        "order_key": ("t_end", "t_start", "slice_id"),
    }
    world["rules"]["higher_order_event_time_stress"] = {
        "relevant_rounds": 5,
        "out_of_order_block_size": 4,
        "out_of_order_pattern": (4, 2, 1, 3),
        "late_conflict_event_time": 10.0,
    }
    return world


def initial_nov_needs_028(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
