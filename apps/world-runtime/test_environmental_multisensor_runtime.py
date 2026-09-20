from copy import deepcopy

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from environmental_perception import project_environmental_presence
from environmental_sensor_runtime import project_environmental_sensor_readings
from memoria_v2_adapter import observer_state_addresses
from scenario_life_gate_007 import build_life_gate_007_world


def _bands(tick):
    return {sample.sensor_id: sample.band_id for sample in tick.samples}


def test_multimodal_frame_is_synchronized_across_all_channels():
    world = build_life_gate_007_world()
    tick = sample_multimodal_sensor_frame(world, observer_id="nova")

    assert len(tick.samples) == 4
    assert {sample.frame_id for sample in tick.samples} == {tick.frame_id}
    assert _bands(tick) == {
        "s_flow": "d0",
        "s_intensity": "i2",
        "s_presence": "p1",
        "s_trend": "t0",
    }
    assert tick.event["frame_id"] == tick.frame_id
    assert tick.event["after"]["channel_count"] == 4


def test_multimodal_frame_changes_after_distributed_flow():
    world = build_life_gate_007_world()
    initial = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = initial.world

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    after = sample_multimodal_sensor_frame(world, observer_id="nova")

    assert _bands(after) == {
        "s_flow": "d1",
        "s_intensity": "i1",
        "s_presence": "p1",
        "s_trend": "t2",
    }
    assert len({sample.frame_id for sample in after.samples}) == 1


def test_multimodal_projection_contains_independent_readings_without_composite_label():
    world = build_life_gate_007_world()
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    projected = project_environmental_presence(world, "nova")
    projected = project_environmental_sensor_readings(projected, "nova")
    state = observer_state_addresses(projected, "nova")

    sensor_relations = [
        address for address in state if address.startswith("live:relation:rel_sensor_")
    ]
    assert len(sensor_relations) == 4

    serialized = "|".join(state)
    for forbidden in (
        "water_falling",
        "water_flowing",
        "high_water",
        "low_water",
        "multimodal_context",
        "raw_value",
        "source_value",
    ):
        assert forbidden not in serialized


def test_same_channel_tuple_hides_different_exact_quantities():
    base = build_life_gate_007_world()

    a = deepcopy(base)
    da = a["entities"]["water_01"]["components"]["environmental_distribution"]
    da["by_region"] = {"spring": 40}
    da["initial_total"] = 40
    a = sample_multimodal_sensor_frame(a, observer_id="nova").world

    b = deepcopy(base)
    db = b["entities"]["water_01"]["components"]["environmental_distribution"]
    db["by_region"] = {"spring": 80}
    db["initial_total"] = 80
    b = sample_multimodal_sensor_frame(b, observer_id="nova").world

    pa = project_environmental_sensor_readings(project_environmental_presence(a, "nova"), "nova")
    pb = project_environmental_sensor_readings(project_environmental_presence(b, "nova"), "nova")

    assert observer_state_addresses(pa, "nova") == observer_state_addresses(pb, "nova")


def test_second_physical_tick_produces_next_temporal_multisensor_state():
    world = build_life_gate_007_world()
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    second = sample_multimodal_sensor_frame(world, observer_id="nova")

    assert _bands(second) == {
        "s_flow": "d0",
        "s_intensity": "i0",
        "s_presence": "p1",
        "s_trend": "t2",
    }


def test_multimodal_sampling_is_deterministic():
    world = build_life_gate_007_world()

    a = sample_multimodal_sensor_frame(world, observer_id="nova")
    b = sample_multimodal_sensor_frame(world, observer_id="nova")

    assert a.samples == b.samples
    assert a.event == b.event
    assert a.delta == b.delta
