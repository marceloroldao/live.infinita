from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_003 import build_life_gate_003_world


DEFAULT_ROUTE_PROPERTIES = {
    "spring_channel": {
        "capacity": 8,
        "descent": 6,
        "retention": 2,
        "evaporation": 3,
    },
    "spring_hollow": {
        "capacity": 5,
        "descent": 4,
        "retention": 7,
        "evaporation": 1,
    },
}


def build_life_gate_004_world() -> dict:
    """Water chooses among local routes from world-owned numeric properties."""
    world = deepcopy(build_life_gate_003_world())
    world["world_id"] = "life-gate-004"

    # Remove the fixed-route scheduler from Gate 003.
    world["rules"].pop("environmental_agents", None)
    world["rules"]["environmental_reactive_agents"] = [
        {
            "rule_id": "water_local_route_choice",
            "agent": "water_01",
            "min_ticks": 1,
            "selectors": [
                {"property": "capacity", "order": "desc"},
                {"property": "descent", "order": "desc"},
                {"property": "retention", "order": "asc"},
                {"property": "evaporation", "order": "asc"},
            ],
        }
    ]

    world["regions"] = {
        "spring": {
            "environmental_routes": [
                {
                    "route_id": "spring_channel",
                    "to_region": "channel",
                    "trace_address": "live:environment:trace:spring-channel",
                    "properties": deepcopy(DEFAULT_ROUTE_PROPERTIES["spring_channel"]),
                },
                {
                    "route_id": "spring_hollow",
                    "to_region": "hollow",
                    "trace_address": "live:environment:trace:spring-hollow",
                    "properties": deepcopy(DEFAULT_ROUTE_PROPERTIES["spring_hollow"]),
                },
            ]
        },
        "channel": {
            "environmental_routes": [
                {
                    "route_id": "channel_basin",
                    "to_region": "basin",
                    "trace_address": "live:environment:trace:channel-basin",
                    "properties": {
                        "capacity": 7,
                        "descent": 5,
                        "retention": 2,
                        "evaporation": 2,
                    },
                }
            ]
        },
        "hollow": {
            "environmental_routes": [
                {
                    "route_id": "hollow_basin",
                    "to_region": "basin",
                    "trace_address": "live:environment:trace:hollow-basin",
                    "properties": {
                        "capacity": 4,
                        "descent": 2,
                        "retention": 8,
                        "evaporation": 1,
                    },
                }
            ]
        },
        "basin": {"environmental_routes": []},
    }
    return world


def initial_nov_needs_004(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
