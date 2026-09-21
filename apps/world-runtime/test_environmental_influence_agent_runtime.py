from copy import deepcopy

from environmental_influence_agent_runtime import (
    advance_environmental_influence_agents,
)
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from multiagent_environment_runtime import (
    advance_coupled_environmental_step,
    preview_next_agent_conditioned_sensor_futures,
)
from scenario_life_gate_014 import build_life_gate_014_world


def _route_available(world):
    route = next(
        item
        for item in world["regions"]["spring"]["environmental_routes"]
        if item["route_id"] == "spring_channel"
    )
    return route.get("available", True)


def _flow_band(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_flow"]["band_id"]
    )


def test_wind_gust_autonomously_opens_channel_and_advances_phase():
    world = build_life_gate_014_world(episode_id=1, wind_phase_id="w_gust_a")
    before = deepcopy(world)

    tick = advance_environmental_influence_agents(world, ticks=1)[0]

    assert world == before
    assert _route_available(tick.world) is True

    wind = tick.world["entities"]["wind_01"]["components"]["environmental_state"]
    assert wind["phase_id"] == "w_gust_b"
    assert wind["last_action_id"] == "wind_open_channel"
    assert wind["generation"] == 1

    assert tick.event["actor"] == "wind_01"
    assert tick.event["influences"][0]["phase_id"] == "w_gust_a"
    assert tick.event["influences"][0]["action_id"] == "wind_open_channel"
    assert tick.event["influences"][0]["next_phase_id"] == "w_gust_b"
    assert any(
        operation["path"].endswith("/environmental_routes/0/available")
        and operation["value"] is True
        for operation in tick.delta["operations"]
    )


def test_wind_lull_autonomously_closes_channel_and_advances_phase():
    world = build_life_gate_014_world(episode_id=2, wind_phase_id="w_lull_a")

    tick = advance_environmental_influence_agents(world, ticks=1)[0]

    assert _route_available(tick.world) is False
    wind = tick.world["entities"]["wind_01"]["components"]["environmental_state"]
    assert wind["phase_id"] == "w_lull_b"
    assert wind["last_action_id"] == "wind_close_channel"
    assert tick.event["actor"] == "wind_01"
    assert tick.event["influences"][0]["phase_id"] == "w_lull_a"
    assert tick.event["influences"][0]["action_id"] == "wind_close_channel"
    assert tick.event["influences"][0]["next_phase_id"] == "w_lull_b"


def test_wind_phase_cycle_is_endogenous_and_deterministic():
    world = build_life_gate_014_world(episode_id=3, wind_phase_id="w_gust_a")

    first = advance_environmental_influence_agents(world, ticks=1)[0]
    second = advance_environmental_influence_agents(first.world, ticks=1)[0]
    third = advance_environmental_influence_agents(second.world, ticks=1)[0]
    fourth = advance_environmental_influence_agents(third.world, ticks=1)[0]

    assert first.event["influences"][0]["action_id"] == "wind_open_channel"
    assert second.event["influences"][0]["action_id"] == "wind_open_channel"
    assert third.event["influences"][0]["action_id"] == "wind_close_channel"
    assert fourth.event["influences"][0]["action_id"] == "wind_close_channel"

    state = fourth.world["entities"]["wind_01"]["components"]["environmental_state"]
    assert state["phase_id"] == "w_gust_a"
    assert state["generation"] == 4


def test_same_observer_state_different_wind_phase_changes_water_future():
    gust = build_life_gate_014_world(episode_id=4, wind_phase_id="w_gust_a")
    lull = build_life_gate_014_world(episode_id=5, wind_phase_id="w_lull_a")
    gust = sample_multimodal_sensor_frame(gust, observer_id="nova").world
    lull = sample_multimodal_sensor_frame(lull, observer_id="nova").world

    assert _flow_band(gust) == _flow_band(lull) == "d0"

    gust_future = preview_next_agent_conditioned_sensor_futures(
        gust,
        observer_id="nova",
        sensor_id="s_flow",
    )
    lull_future = preview_next_agent_conditioned_sensor_futures(
        lull,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert gust_future.candidates[0].influence_agent_id == "wind_01"
    assert gust_future.candidates[0].influence_phase_id == "w_gust_a"
    assert gust_future.candidates[0].influence_action_id == "wind_open_channel"
    assert gust_future.candidates[0].influence_next_phase_id == "w_gust_b"
    assert gust_future.candidates[0].band_id == "d1"

    assert lull_future.candidates[0].influence_agent_id == "wind_01"
    assert lull_future.candidates[0].influence_phase_id == "w_lull_a"
    assert lull_future.candidates[0].influence_action_id == "wind_close_channel"
    assert lull_future.candidates[0].influence_next_phase_id == "w_lull_b"
    assert lull_future.candidates[0].band_id == "d2"


def test_agent_conditioned_preview_matches_autonomous_commit():
    for episode_id, phase_id, expected in (
        (6, "w_gust_a", "d1"),
        (7, "w_lull_a", "d2"),
    ):
        world = build_life_gate_014_world(
            episode_id=episode_id,
            wind_phase_id=phase_id,
        )
        world = sample_multimodal_sensor_frame(world, observer_id="nova").world

        preview = preview_next_agent_conditioned_sensor_futures(
            world,
            observer_id="nova",
            sensor_id="s_flow",
        )
        committed = advance_coupled_environmental_step(
            world,
            observer_id="nova",
        )

        assert preview.candidates[0].band_id == expected
        assert _flow_band(committed.world) == expected
        assert (
            preview.candidates[0].influence_action_id
            == committed.influence.influences[0]["action_id"]
        )


def test_autonomous_coupled_step_records_wind_then_water_then_sensor_causality():
    world = build_life_gate_014_world(episode_id=8, wind_phase_id="w_gust_a")
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    step = advance_coupled_environmental_step(
        world,
        observer_id="nova",
    )

    assert step.influence.event["tick_id"] + 1 == step.distributed.event["tick_id"]
    assert step.distributed.event["tick_id"] + 1 == step.sensor.event["tick_id"]
    assert step.influence.event["actor"] == "wind_01"
    assert step.influence.influences[0]["action_id"] == "wind_open_channel"
    assert step.sensor.samples
    assert _flow_band(step.world) == "d1"


def test_agent_conditioned_preview_is_read_only_and_hides_exact_water_quantity():
    world = build_life_gate_014_world(episode_id=9, wind_phase_id="w_lull_a")
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    before = deepcopy(world)

    preview = preview_next_agent_conditioned_sensor_futures(
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert world == before
    serialized = repr(preview).lower()
    for forbidden in (
        "by_region",
        "initial_total",
        "evaporated_total",
        "environmental_distribution",
        "raw_value",
        "source_value",
    ):
        assert forbidden not in serialized


def test_agent_conditioned_preview_is_deterministic():
    world = build_life_gate_014_world(episode_id=10, wind_phase_id="w_gust_a")
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    a = preview_next_agent_conditioned_sensor_futures(
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )
    b = preview_next_agent_conditioned_sensor_futures(
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert a == b
