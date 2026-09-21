from __future__ import annotations

from copy import deepcopy

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from reality_slice import TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_branching_runtime import (
    commit_branching_environmental_state,
)
from environmental_branching_temporal_prediction_runtime import (
    predict_branching_environmental_sensor,
)
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import reality_window_from_world_rule
from scenario_life_gate_013 import build_life_gate_013_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


def _branch_episode(episode_id: int, control_state_id: str):
    world = build_life_gate_013_world(episode_id=episode_id)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    committed = commit_branching_environmental_state(
        world,
        observer_id="nova",
        control_state_id=control_state_id,
    )
    world = committed.world

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
    ).world

    return world, reality_window_from_world_rule(
        world,
        observer_id="nova",
    )


def _memory_from_branch_episodes(open_ids=(), closed_ids=()):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in open_ids:
        world, window = _branch_episode(episode_id, "v_channel_open")
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    for episode_id in closed_ids:
        world, window = _branch_episode(episode_id, "v_channel_closed")
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    if last_world is None:
        return StructuralTemporalObservationMemory(), engine

    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    memory = StructuralTemporalObservationMemory()
    for candidate in admitted_candidates(decisions):
        ingest_temporal_evidence_candidate(memory, candidate)
    return memory, engine


def _fresh_world(episode_id: int):
    world = build_life_gate_013_world(episode_id=episode_id)
    return sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
    ).world


def _branch_for_candidate(prediction, candidate_id):
    return next(
        item
        for item in prediction.physical_futures.candidates
        if item.candidate_id == candidate_id
    )


def _flow_band(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_flow"]["band_id"]
    )


def test_life_gate_013_world_generates_two_physical_futures_before_memoria():
    memory, _engine = _memory_from_branch_episodes(
        open_ids=(601, 602, 603),
    )
    world = _fresh_world(610)

    prediction = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert prediction.current_band_id == "d0"
    assert len(prediction.physical_futures.candidates) == 2
    assert {
        (item.control_state_id, item.band_id)
        for item in prediction.physical_futures.candidates
    } == {
        ("v_channel_open", "d1"),
        ("v_channel_closed", "d2"),
    }


def test_life_gate_013_open_only_memory_can_recognize_open_branch_but_not_choose_valve():
    memory, _engine = _memory_from_branch_episodes(
        open_ids=(611, 612, 613),
    )
    world = _fresh_world(620)

    prediction = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert prediction.resolution.resolved is True
    assert prediction.resolution.ambiguous is False
    assert prediction.resolution.resolved_candidate is not None

    recognized = _branch_for_candidate(
        prediction,
        prediction.resolution.resolved_candidate.candidate_id,
    )
    assert recognized.control_state_id == "v_channel_open"
    assert recognized.band_id == "d1"

    # Physical authority still belongs to an explicit external control input.
    committed = commit_branching_environmental_state(
        world,
        observer_id="nova",
        control_state_id="v_channel_closed",
    )
    assert committed.control_state_id == "v_channel_closed"
    assert _flow_band(committed.world) == "d2"


def test_life_gate_013_both_learned_physical_futures_remain_ambiguous():
    memory, engine = _memory_from_branch_episodes(
        open_ids=(621, 622, 623),
        closed_ids=(624, 625, 626),
    )
    world = _fresh_world(630)

    prediction = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert len(prediction.physical_futures.candidates) == 2
    assert prediction.resolution.resolved is False
    assert prediction.resolution.ambiguous is True
    assert prediction.resolution.resolved_candidate is None
    assert prediction.resolution.reason == "multiple-supported-world-continuations"
    assert {
        _branch_for_candidate(prediction, item.candidate.candidate_id).control_state_id
        for item in prediction.resolution.matches
    } == {
        "v_channel_open",
        "v_channel_closed",
    }

    # Both temporal relations reached independent upstream evidence.
    assert len(engine.links) > 0


def test_life_gate_013_stronger_history_does_not_break_legitimate_physical_ambiguity():
    memory, engine = _memory_from_branch_episodes(
        open_ids=(631, 632, 633, 634, 635, 636),
        closed_ids=(637, 638, 639),
    )
    world = _fresh_world(640)

    prediction = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert prediction.resolution.resolved is False
    assert prediction.resolution.ambiguous is True
    assert prediction.resolution.reason == "multiple-supported-world-continuations"

    # Gate 011/013 intentionally does not rank supported concrete futures by rho.
    matched_states = {
        _branch_for_candidate(prediction, item.candidate.candidate_id).control_state_id
        for item in prediction.resolution.matches
    }
    assert matched_states == {"v_channel_open", "v_channel_closed"}

    # Verify there actually is unequal learned strength somewhere for this pair family.
    rhos = sorted(link.rho for link in engine.links.values())
    assert rhos[-1] > rhos[0]


def test_life_gate_013_empty_memory_preserves_two_physical_futures_without_recognition():
    memory = StructuralTemporalObservationMemory()
    world = _fresh_world(650)

    prediction = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert len(prediction.physical_futures.candidates) == 2
    assert prediction.resolution.resolved is False
    assert prediction.resolution.ambiguous is False
    assert prediction.resolution.matches == ()
    assert prediction.resolution.reason == "no-supported-world-continuation"


def test_life_gate_013_prediction_is_read_only_over_world_and_memory():
    memory, _engine = _memory_from_branch_episodes(
        open_ids=(651, 652, 653),
        closed_ids=(654, 655, 656),
    )
    world = _fresh_world(660)
    world_before = deepcopy(world)
    memory_before = memory.snapshot()

    _ = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert world == world_before
    assert memory.snapshot() == memory_before


def test_life_gate_013_memoria_resolution_contains_no_hidden_physical_values():
    memory, _engine = _memory_from_branch_episodes(
        open_ids=(661, 662, 663),
        closed_ids=(664, 665, 666),
    )
    world = _fresh_world(670)

    prediction = predict_branching_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    serialized = repr(prediction.resolution).lower()
    for forbidden in (
        "by_region",
        "initial_total",
        "evaporated_total",
        "environmental_distribution",
        "raw_value",
        "source_value",
    ):
        assert forbidden not in serialized


def test_life_gate_013_is_deterministic():
    memory_a, _engine_a = _memory_from_branch_episodes(
        open_ids=(671, 672, 673),
        closed_ids=(674, 675, 676),
    )
    memory_b, _engine_b = _memory_from_branch_episodes(
        open_ids=(671, 672, 673),
        closed_ids=(674, 675, 676),
    )
    world_a = _fresh_world(680)
    world_b = _fresh_world(680)

    a = predict_branching_environmental_sensor(
        memory_a,
        world_a,
        observer_id="nova",
        sensor_id="s_flow",
    )
    b = predict_branching_environmental_sensor(
        memory_b,
        world_b,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert a == b
