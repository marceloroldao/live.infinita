from copy import deepcopy

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_context_runtime import apply_environmental_context_constraints
from environmental_influence_agent_runtime import advance_environmental_influence_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from scenario_life_gate_016 import build_life_gate_016_world


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


def _consequence(context_state_id):
    world = build_life_gate_016_world(
        episode_id=1,
        context_state_id=context_state_id,
    )
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    ).world
    influence = advance_environmental_influence_agents(world, ticks=1)[0]
    constrained = apply_environmental_context_constraints(influence.world)
    physical = advance_distributed_environmental_agents(
        constrained.world,
        ticks=1,
    )[0]
    sensed = sample_multimodal_sensor_frame(
        physical.world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )
    return world, influence, constrained, physical, sensed


def test_clear_context_preserves_wind_open_route_and_produces_d1():
    _world, influence, constrained, _physical, sensed = _consequence("ctx_clear")

    assert influence.influences[0]["action_id"] == "wind_open_channel"
    assert _route_available(influence.world) is True
    assert _route_available(constrained.world) is True
    assert _flow_band(sensed.world) == "d1"
    assert constrained.constraints[0]["state_id"] == "ctx_clear"


def test_blocked_context_overrides_same_wind_action_and_produces_d2():
    _world, influence, constrained, _physical, sensed = _consequence("ctx_blocked")

    assert influence.influences[0]["action_id"] == "wind_open_channel"
    assert _route_available(influence.world) is True
    assert _route_available(constrained.world) is False
    assert _flow_band(sensed.world) == "d2"
    assert constrained.constraints[0]["state_id"] == "ctx_blocked"


def test_context_runtime_is_read_only_over_input_and_auditable():
    world = build_life_gate_016_world(
        episode_id=2,
        context_state_id="ctx_blocked",
    )
    influence = advance_environmental_influence_agents(world, ticks=1)[0]
    before = deepcopy(influence.world)

    constrained = apply_environmental_context_constraints(influence.world)

    assert influence.world == before
    assert constrained.event["type"] == "environmental_context_applied"
    assert constrained.event["constraints"][0]["entity_id"] == "barrier_01"
    assert constrained.event["constraints"][0]["state_id"] == "ctx_blocked"
    assert constrained.delta["provenance"]["origin"] == "environmental-context-runtime"
    assert any(
        operation["path"].endswith("/available")
        and operation["value"] is False
        for operation in constrained.delta["operations"]
    )


def test_context_signal_is_opaque_in_public_sensor_event():
    world = build_life_gate_016_world(
        episode_id=3,
        context_state_id="ctx_blocked",
    )
    tick = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=("s_context_signal_01",),
    )

    assert tick.samples[0].band_id == "c1"
    reading = (
        tick.world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_context_signal_01"]
    )
    assert reading["source_value"] == "ctx_blocked"

    serialized = repr(tick.event).lower()
    assert "ctx_blocked" not in serialized
    assert "route_barrier" not in serialized
    assert tick.event["channels"][0]["band_id"] == "c1"


def test_context_runtime_is_deterministic():
    world = build_life_gate_016_world(
        episode_id=4,
        context_state_id="ctx_clear",
    )
    a = apply_environmental_context_constraints(world)
    b = apply_environmental_context_constraints(world)

    assert a == b
