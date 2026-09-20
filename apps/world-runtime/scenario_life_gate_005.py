from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_004 import build_life_gate_004_world


def build_life_gate_005_world() -> dict:
    """Convert Water from one position into a conserved distributed quantity."""
    world = deepcopy(build_life_gate_004_world())
    world["world_id"] = "life-gate-005"

    world["rules"].pop("environmental_reactive_agents", None)
    world["rules"]["environmental_distributed_agents"] = [
        {
            "rule_id": "water_distributed_balance",
            "agent": "water_01",
            "min_ticks": 1,
            "distribution_component": "environmental_distribution",
            "region_retention_property": "retention_units",
            "region_evaporation_property": "evaporation_units",
            "route_capacity_property": "capacity",
        }
    ]

    water = world["entities"]["water_01"]
    water["components"]["transform"] = {"region_id": "distributed"}
    water["components"]["environmental_distribution"] = {
        "initial_total": 100,
        "by_region": {"spring": 100},
        "evaporated_total": 0,
    }
    water["components"]["environmental_state"]["last_transition_tick"] = int(
        world["current_tick"]
    )
    water["components"]["environmental_state"]["generation"] = 0

    world["regions"]["spring"]["environmental_properties"] = {
        "retention_units": 20,
        "evaporation_units": 10,
    }
    world["regions"]["spring"]["environmental_routes"] = [
        {
            "route_id": "spring_channel",
            "to_region": "channel",
            "trace_address": "live:environment:flow:spring-channel",
            "properties": {"capacity": 40},
        },
        {
            "route_id": "spring_hollow",
            "to_region": "hollow",
            "trace_address": "live:environment:flow:spring-hollow",
            "properties": {"capacity": 30},
        },
    ]

    world["regions"]["channel"]["environmental_properties"] = {
        "retention_units": 10,
        "evaporation_units": 5,
    }
    world["regions"]["channel"]["environmental_routes"] = [
        {
            "route_id": "channel_basin",
            "to_region": "basin",
            "trace_address": "live:environment:flow:channel-basin",
            "properties": {"capacity": 25},
        }
    ]

    world["regions"]["hollow"]["environmental_properties"] = {
        "retention_units": 15,
        "evaporation_units": 3,
    }
    world["regions"]["hollow"]["environmental_routes"] = [
        {
            "route_id": "hollow_basin",
            "to_region": "basin",
            "trace_address": "live:environment:flow:hollow-basin",
            "properties": {"capacity": 12},
        }
    ]

    world["regions"]["basin"]["environmental_properties"] = {
        "retention_units": 1_000,
        "evaporation_units": 2,
    }
    world["regions"]["basin"]["environmental_routes"] = []

    return world


def initial_nov_needs_005(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
