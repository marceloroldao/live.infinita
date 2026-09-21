from copy import deepcopy

from environmental_branching_runtime import (
    commit_branching_environmental_state,
    enumerate_branching_distributed_sensor_candidates,
)
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from scenario_life_gate_013 import build_life_gate_013_world


def _bands_by_state(future_set, sensor_id):
    return {
        candidate.control_state_id: candidate.band_id
        for candidate in future_set.candidates
        if candidate.sensor_id == sensor_id
    }


def test_branching_runtime_enumerates_two_genuine_physical_flow_futures():
    world = build_life_gate_013_world(episode_id=1)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )

    assert future.control_id == "spring_channel_valve"
    assert len(future.candidates) == 2
    assert _bands_by_state(future, "s_flow") == {
        "v_channel_closed": "d2",
        "v_channel_open": "d1",
    }
    assert len({item.branch_id for item in future.candidates}) == 2


def test_branching_runtime_also_changes_intensity_as_physical_consequence():
    world = build_life_gate_013_world(episode_id=2)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_intensity",),
    )

    assert _bands_by_state(future, "s_intensity") == {
        "v_channel_closed": "i2",
        "v_channel_open": "i1",
    }


def test_each_branch_preview_matches_explicit_external_commit():
    world = build_life_gate_013_world(episode_id=3)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )
    expected = {
        item.control_state_id: item.band_id
        for item in future.candidates
    }

    for state_id in ("v_channel_open", "v_channel_closed"):
        committed = commit_branching_environmental_state(
            world,
            observer_id="nova",
            control_state_id=state_id,
        )
        reading = (
            committed.world["entities"]["nova"]["components"]["sensor_state"]["readings"]
            ["s_flow"]
        )
        assert reading["band_id"] == expected[state_id]
        assert committed.control_state_id == state_id


def test_branching_preview_is_read_only_over_source_world():
    world = build_life_gate_013_world(episode_id=4)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    before = deepcopy(world)

    _ = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_flow",),
    )

    assert world == before


def test_branching_candidates_do_not_expose_hidden_exact_distribution_values():
    world = build_life_gate_013_world(episode_id=5)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    future = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_flow", "s_intensity"),
    )

    serialized = repr(future).lower()
    for forbidden in (
        "by_region",
        "initial_total",
        "evaporated_total",
        "raw_value",
        "source_value",
        "environmental_distribution",
    ):
        assert forbidden not in serialized


def test_branching_runtime_rejects_non_admissible_external_commit():
    world = build_life_gate_013_world(episode_id=6)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    try:
        commit_branching_environmental_state(
            world,
            observer_id="nova",
            control_state_id="v_invalid",
        )
    except ValueError as exc:
        assert "not physically admissible" in str(exc)
    else:
        raise AssertionError("invalid external branch must be rejected")


def test_branching_runtime_is_deterministic():
    world = build_life_gate_013_world(episode_id=7)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    a = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_flow", "s_intensity"),
    )
    b = enumerate_branching_distributed_sensor_candidates(
        world,
        observer_id="nova",
        sensor_ids=("s_flow", "s_intensity"),
    )

    assert a == b
