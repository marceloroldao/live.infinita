from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_013 import build_life_gate_013_world


def build_life_gate_014_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
) -> dict:
    """Replace the abstract external valve branch with autonomous Wind influence."""
    if wind_phase_id not in {"w_gust_a", "w_gust_b", "w_lull_a", "w_lull_b"}:
        raise ValueError("unsupported wind_phase_id")

    world = deepcopy(build_life_gate_013_world(episode_id=episode_id))
    world["world_id"] = f"life-gate-014-{wind_phase_id}-episode-{episode_id}"

    # Gate 014 removes the abstract external-control authority from Gate 013.
    world["rules"].pop("environmental_branching_control", None)
    world["entities"].pop("valve_spring_channel_01", None)

    world["entities"]["wind_01"] = {
        "entity_id": "wind_01",
        "class": "environmental_agent",
        "type": "wind",
        "status": "active",
        "version": int(world["current_version"]),
        "created_at_tick": int(world["current_tick"]),
        "components": {
            "transform": {
                "region_id": "spring",
            },
            "environmental_state": {
                "phase_id": wind_phase_id,
                "generation": 0,
                "last_transition_tick": int(world["current_tick"]),
            },
        },
    }

    world["rules"]["environmental_influence_agents"] = [
        {
            "rule_id": "wind_spring_channel_cycle",
            "agent": "wind_01",
            "min_ticks": 1,
            "phases": [
                {
                    "phase_id": "w_gust_a",
                    "action_id": "wind_open_channel",
                    "next_phase_id": "w_gust_b",
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": True,
                        }
                    ],
                },
                {
                    "phase_id": "w_gust_b",
                    "action_id": "wind_open_channel",
                    "next_phase_id": "w_lull_a",
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": True,
                        }
                    ],
                },
                {
                    "phase_id": "w_lull_a",
                    "action_id": "wind_close_channel",
                    "next_phase_id": "w_lull_b",
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": False,
                        }
                    ],
                },
                {
                    "phase_id": "w_lull_b",
                    "action_id": "wind_close_channel",
                    "next_phase_id": "w_gust_a",
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": False,
                        }
                    ],
                },
            ],
        }
    ]
    return world


def initial_nov_needs_014(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
