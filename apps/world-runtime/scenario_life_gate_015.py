from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_014 import build_life_gate_014_world


def build_life_gate_015_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
) -> dict:
    """Add an independent opaque sensor signal for the autonomous Wind agent."""
    world = deepcopy(
        build_life_gate_014_world(
            episode_id=episode_id,
            wind_phase_id=wind_phase_id,
        )
    )
    world["world_id"] = f"life-gate-015-{wind_phase_id}-episode-{episode_id}"

    world["rules"]["multimodal_sensors"].append(
        {
            "sensor_id": "s_agent_signal_01",
            "observer": "nova",
            "target": "wind_01",
            "source_component": "environmental_state",
            "source_field": "phase_id",
            "kind": "component_enum",
            "value_band_ids": {
                "w_gust_a": "a0",
                "w_gust_b": "a0",
                "w_lull_a": "a1",
                "w_lull_b": "a1",
            },
        }
    )
    return world


def initial_nov_needs_015(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
