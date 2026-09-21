from copy import deepcopy

from contextual_multiagent_environment_runtime import advance_contextual_multiagent_step
from environmental_context_process_runtime import (
    advance_environmental_context_processes,
)
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from scenario_life_gate_017 import build_life_gate_017_world


def _route_available(world):
    route = next(
        item
        for item in world["regions"]["spring"]["environmental_routes"]
        if item["route_id"] == "spring_channel"
    )
    return route.get("available", True)


def _barrier_phase(world):
    return (
        world["entities"]["barrier_01"]["components"]["process_state"]["phase_id"]
    )


def _flow_band(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_flow"]["band_id"]
    )


def test_context_process_clear_phase_allows_route_and_advances_to_blocked():
    world = build_life_gate_017_world(episode_id=1)
    before = deepcopy(world)

    tick = advance_environmental_context_processes(world, ticks=1)[0]

    assert world == before
    assert _route_available(tick.world) is True
    assert _barrier_phase(tick.world) == "b_blocked"

    transition = tick.transitions[0]
    assert tick.event["actor"] == "barrier_01"
    assert transition["phase_id"] == "b_clear"
    assert transition["action_id"] == "barrier_allow_channel"
    assert transition["next_phase_id"] == "b_blocked"
    assert transition["generation"] == 1


def test_context_process_second_tick_blocks_route_and_cycles_to_clear():
    world = build_life_gate_017_world(episode_id=2)

    first = advance_environmental_context_processes(world, ticks=1)[0]
    second = advance_environmental_context_processes(first.world, ticks=1)[0]

    assert _route_available(first.world) is True
    assert _barrier_phase(first.world) == "b_blocked"

    assert _route_available(second.world) is False
    assert _barrier_phase(second.world) == "b_clear"
    assert second.transitions[0]["action_id"] == "barrier_block_channel"
    assert second.transitions[0]["generation"] == 2


def test_context_process_event_delta_are_authoritative_and_auditable():
    world = build_life_gate_017_world(episode_id=3)

    tick = advance_environmental_context_processes(world, ticks=1)[0]

    assert tick.event["type"] == "environmental_context_process_tick"
    assert tick.event["provenance"]["origin"] == (
        "environmental-context-process-runtime"
    )
    assert tick.delta["provenance"]["origin"] == (
        "environmental-context-process-runtime"
    )
    assert any(
        operation["path"].endswith("/available")
        and operation["value"] is True
        for operation in tick.delta["operations"]
    )
    assert any(
        operation["path"].endswith("/components/process_state")
        for operation in tick.delta["operations"]
    )


def test_one_world_evolves_clear_then_blocked_while_wind_stays_in_gust_family():
    world = build_life_gate_017_world(episode_id=4)
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    ).world
    assert _flow_band(world) == "d0"

    first = advance_contextual_multiagent_step(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )
    second = advance_contextual_multiagent_step(
        first.world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )

    assert first.influence.influences[0]["phase_id"] == "w_gust_a"
    assert first.influence.influences[0]["action_id"] == "wind_open_channel"
    assert first.context.transitions[0]["phase_id"] == "b_clear"
    assert first.context.transitions[0]["action_id"] == "barrier_allow_channel"
    assert _flow_band(first.world) == "d1"

    assert second.influence.influences[0]["phase_id"] == "w_gust_b"
    assert second.influence.influences[0]["action_id"] == "wind_open_channel"
    assert second.context.transitions[0]["phase_id"] == "b_blocked"
    assert second.context.transitions[0]["action_id"] == "barrier_block_channel"
    assert _flow_band(second.world) == "d0"


def test_coupled_order_is_wind_then_context_then_water_then_sensor():
    world = build_life_gate_017_world(episode_id=5)

    step = advance_contextual_multiagent_step(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )

    assert step.influence.event["tick_id"] + 1 == step.context.event["tick_id"]
    assert step.context.event["tick_id"] + 1 == step.distributed.event["tick_id"]
    assert step.distributed.event["tick_id"] + 1 == step.sensor.event["tick_id"]


def test_context_process_is_deterministic():
    world = build_life_gate_017_world(episode_id=6)

    a = advance_environmental_context_processes(world, ticks=2)
    b = advance_environmental_context_processes(world, ticks=2)

    assert a == b
