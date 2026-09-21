from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_012 import build_life_gate_012_world


def build_life_gate_013_world(*, episode_id: int = 0) -> dict:
    """Add one genuine external-control branch to the environmental physics."""
    world = deepcopy(build_life_gate_012_world(episode_id=episode_id))
    world["world_id"] = f"life-gate-013-episode-{episode_id}"

    world["entities"]["valve_spring_channel_01"] = {
        "entity_id": "valve_spring_channel_01",
        "class": "environmental_control",
        "type": "route_valve",
        "status": "active",
        "version": int(world["current_version"]),
        "created_at_tick": int(world["current_tick"]),
        "components": {
            "environmental_control": {
                "control_id": "spring_channel_valve",
                "state_id": "unresolved_external",
            },
            "transform": {
                "region_id": "spring",
            },
        },
    }

    world["rules"]["environmental_branching_control"] = {
        "control_id": "spring_channel_valve",
        "entity_id": "valve_spring_channel_01",
        "runtime": "distributed_environmental",
        "lookahead_ticks": 1,
        "admissible_next_states": [
            {
                "state_id": "v_channel_open",
                "route_overrides": [
                    {
                        "region_id": "spring",
                        "route_id": "spring_channel",
                        "available": True,
                    }
                ],
            },
            {
                "state_id": "v_channel_closed",
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
    return world


def initial_nov_needs_013(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
