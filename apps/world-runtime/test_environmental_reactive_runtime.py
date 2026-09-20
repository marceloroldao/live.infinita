from copy import deepcopy

from environmental_agent_runtime import advance_reactive_environmental_agents
from scenario_life_gate_004 import build_life_gate_004_world
from world_property_runtime import update_environmental_route_properties


def _water_region(world):
    return world["entities"]["water_01"]["components"]["transform"]["region_id"]


def _transition(world):
    tick = advance_reactive_environmental_agents(world, ticks=1)[0]
    assert len(tick.transitions) == 1
    return tick


def test_reactive_water_prefers_declared_default_route_properties():
    world = build_life_gate_004_world()
    tick = _transition(world)

    transition = tick.transitions[0]
    assert transition["route_id"] == "spring_channel"
    assert transition["to_region"] == "channel"
    assert _water_region(tick.world) == "channel"
    assert transition["route_properties"]["capacity"] == 8


def test_changing_only_world_route_properties_changes_water_path():
    world = build_life_gate_004_world()
    world = update_environmental_route_properties(
        world,
        region_id="spring",
        route_id="spring_channel",
        properties={
            "capacity": 2,
            "descent": 6,
            "retention": 2,
            "evaporation": 3,
        },
    )
    world = update_environmental_route_properties(
        world,
        region_id="spring",
        route_id="spring_hollow",
        properties={
            "capacity": 9,
            "descent": 4,
            "retention": 7,
            "evaporation": 1,
        },
    )

    tick = _transition(world)
    assert tick.transitions[0]["route_id"] == "spring_hollow"
    assert tick.transitions[0]["to_region"] == "hollow"
    assert _water_region(tick.world) == "hollow"


def test_reactive_selector_falls_through_capacity_to_descent():
    world = build_life_gate_004_world()
    world["regions"]["spring"]["environmental_routes"][0]["properties"] = {
        "capacity": 8,
        "descent": 3,
        "retention": 2,
        "evaporation": 3,
    }
    world["regions"]["spring"]["environmental_routes"][1]["properties"] = {
        "capacity": 8,
        "descent": 7,
        "retention": 7,
        "evaporation": 1,
    }

    tick = _transition(world)
    assert tick.transitions[0]["route_id"] == "spring_hollow"


def test_reactive_selector_falls_through_to_lower_retention():
    world = build_life_gate_004_world()
    world["regions"]["spring"]["environmental_routes"][0]["properties"] = {
        "capacity": 8,
        "descent": 6,
        "retention": 5,
        "evaporation": 1,
    }
    world["regions"]["spring"]["environmental_routes"][1]["properties"] = {
        "capacity": 8,
        "descent": 6,
        "retention": 2,
        "evaporation": 9,
    }

    tick = _transition(world)
    assert tick.transitions[0]["route_id"] == "spring_hollow"


def test_reactive_selector_falls_through_to_lower_evaporation():
    world = build_life_gate_004_world()
    world["regions"]["spring"]["environmental_routes"][0]["properties"] = {
        "capacity": 8,
        "descent": 6,
        "retention": 2,
        "evaporation": 5,
    }
    world["regions"]["spring"]["environmental_routes"][1]["properties"] = {
        "capacity": 8,
        "descent": 6,
        "retention": 2,
        "evaporation": 1,
    }

    tick = _transition(world)
    assert tick.transitions[0]["route_id"] == "spring_hollow"


def test_route_property_update_is_authoritative_and_append_only():
    world = build_life_gate_004_world()
    before = deepcopy(world)

    changed = update_environmental_route_properties(
        world,
        region_id="spring",
        route_id="spring_channel",
        properties={
            "capacity": 3,
            "descent": 6,
            "retention": 2,
            "evaporation": 3,
        },
    )

    assert world == before
    assert changed["current_tick"] == world["current_tick"] + 1
    assert changed["current_version"] == world["current_version"] + 1

    event = next(
        event
        for event in changed["events"].values()
        if event.get("type") == "environmental_route_properties_changed"
    )
    assert event["region_id"] == "spring"
    assert event["route_id"] == "spring_channel"
    assert event["before"]["properties"]["capacity"] == 8
    assert event["after"]["properties"]["capacity"] == 3
    assert event["delta_id"] in changed["deltas"]


def test_reactive_route_choice_is_deterministic():
    def signature():
        world = build_life_gate_004_world()
        ticks = advance_reactive_environmental_agents(world, ticks=2)
        return tuple(
            tuple(
                (
                    item["route_id"],
                    item["from_region"],
                    item["to_region"],
                    tuple(sorted(item["route_properties"].items())),
                )
                for item in tick.transitions
            )
            for tick in ticks
        )

    assert signature() == signature()
