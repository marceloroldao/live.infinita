from copy import deepcopy

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_future_runtime import enumerate_next_distributed_sensor_candidates
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from scenario_life_gate_012 import build_life_gate_012_world


def _bands(future_set):
    return {
        candidate.sensor_id: candidate.band_id
        for candidate in future_set.candidates
    }


def test_physical_future_preview_uses_runtime_physics_for_all_sensor_channels():
    world = build_life_gate_012_world(episode_id=1)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id="nova",
    )

    assert _bands(future) == {
        "s_flow": "d1",
        "s_intensity": "i1",
        "s_presence": "p1",
        "s_trend": "t2",
    }
    assert len(future.candidates) == 4
    assert {item.physical_tick for item in future.candidates} == {
        world["current_tick"] + 1
    }
    assert {item.sensor_tick for item in future.candidates} == {
        world["current_tick"] + 2
    }


def test_physical_future_preview_matches_actual_committed_physics_and_sensor_sample():
    world = build_life_gate_012_world(episode_id=2)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id="nova",
    )

    physical = advance_distributed_environmental_agents(world, ticks=1)[0]
    sensed = sample_multimodal_sensor_frame(
        physical.world,
        observer_id="nova",
    )

    actual = {
        sample.sensor_id: sample.band_id
        for sample in sensed.samples
    }
    assert _bands(future) == actual


def test_physical_future_preview_is_read_only_over_source_world():
    world = build_life_gate_012_world(episode_id=3)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    before = deepcopy(world)

    _ = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id="nova",
    )

    assert world == before


def test_physical_future_preview_can_filter_to_one_world_generated_sensor_future():
    world = build_life_gate_012_world(episode_id=4)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_intensity",),
    )

    assert len(future.candidates) == 1
    candidate = future.candidates[0]
    assert candidate.sensor_id == "s_intensity"
    assert candidate.band_id == "i1"


def test_physical_future_preview_is_deterministic():
    world = build_life_gate_012_world(episode_id=5)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    a = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id="nova",
    )
    b = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id="nova",
    )

    assert a == b


def test_physical_future_preview_requires_world_declared_runtime_policy():
    world = build_life_gate_012_world(episode_id=6)
    world["rules"].pop("environmental_future_preview")

    try:
        enumerate_next_distributed_sensor_candidates(
            world,
            observer_id="nova",
        )
    except ValueError as exc:
        assert "runtime" in str(exc)
    else:
        raise AssertionError("preview must require world-declared runtime policy")
