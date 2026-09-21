from __future__ import annotations

from dataclasses import replace

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from reality_slice import TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_009 import build_life_gate_009_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate
from temporal_prediction_memoria_adapter import (
    resolve_sensor_temporal_world_candidates,
    temporal_sensor_pattern_address,
)


def _episode(episode_id: int):
    world = build_life_gate_009_world(episode_id=episode_id)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    return world, reality_window_from_world_rule(world, observer_id="nova")


def _selector_candidates(episode_ids):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in episode_ids:
        world, window = _episode(episode_id)
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    return engine, admitted_candidates(decisions)


def _memory_from_candidates(candidates):
    memory = StructuralTemporalObservationMemory()
    for candidate in candidates:
        ingest_temporal_evidence_candidate(memory, candidate)
    return memory


def _candidate_for(candidates, sensor_a, band_a, sensor_b, band_b):
    a = sensor_pattern_id(sensor_a, band_a)
    b = sensor_pattern_id(sensor_b, band_b)
    key = (a, b) if a < b else (b, a)
    return next(
        item
        for item in candidates
        if (item.pattern_a, item.pattern_b) == key
    )


def _opposite(orientation: str) -> str:
    return {
        "a_before_b": "b_before_a",
        "b_before_a": "a_before_b",
        "simultaneous": "simultaneous",
    }[orientation]


def test_life_gate_011_three_episodes_select_only_world_offered_supported_continuation():
    _engine, candidates = _selector_candidates((401, 402, 403))
    memory = _memory_from_candidates(candidates)

    resolution = resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(
            ("world_i1", "s_intensity", "i1"),
            ("world_i0", "s_intensity", "i0"),
        ),
    )

    assert resolution.resolved is True
    assert resolution.ambiguous is False
    assert resolution.resolved_candidate is not None
    assert resolution.resolved_candidate.candidate_id == "world_i1"
    assert resolution.resolved_candidate.pattern_address == temporal_sensor_pattern_address(
        "s_intensity",
        "i1",
    )
    assert tuple(item.candidate.candidate_id for item in resolution.matches) == (
        "world_i1",
    )


def test_life_gate_011_memory_cannot_invent_supported_continuation_missing_from_world():
    _engine, candidates = _selector_candidates((411, 412, 413))
    memory = _memory_from_candidates(candidates)

    resolution = resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(("world_i0", "s_intensity", "i0"),),
    )

    assert resolution.resolved is False
    assert resolution.ambiguous is False
    assert resolution.resolved_candidate is None
    assert resolution.matches == ()
    assert resolution.reason == "no-supported-world-continuation"
    assert tuple(candidate.candidate_id for candidate in resolution.candidates) == (
        "world_i0",
    )


def test_life_gate_011_four_episodes_preserve_multiple_supported_world_futures_as_ambiguous():
    engine, candidates = _selector_candidates((421, 422, 423, 424))
    memory = _memory_from_candidates(candidates)

    near = _candidate_for(
        candidates,
        "s_intensity",
        "i2",
        "s_intensity",
        "i1",
    )
    far = _candidate_for(
        candidates,
        "s_intensity",
        "i2",
        "s_intensity",
        "i0",
    )
    assert near.rho > far.rho

    resolution = resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(
            ("world_i1", "s_intensity", "i1"),
            ("world_i0", "s_intensity", "i0"),
        ),
    )

    assert resolution.resolved is False
    assert resolution.ambiguous is True
    assert resolution.resolved_candidate is None
    assert resolution.reason == "multiple-supported-world-continuations"
    assert {item.candidate.candidate_id for item in resolution.matches} == {
        "world_i1",
        "world_i0",
    }

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    i0 = sensor_pattern_id("s_intensity", "i0")
    near_key = (i2, i1) if i2 < i1 else (i1, i2)
    far_key = (i2, i0) if i2 < i0 else (i0, i2)
    assert engine.links[near_key].rho > engine.links[far_key].rho


def test_life_gate_011_supported_opposite_orientation_contests_single_world_future():
    _engine, candidates = _selector_candidates((431, 432, 433))
    near = _candidate_for(
        candidates,
        "s_intensity",
        "i2",
        "s_intensity",
        "i1",
    )
    memory = StructuralTemporalObservationMemory()
    ingest_temporal_evidence_candidate(memory, near)

    opposite = replace(
        near,
        candidate_id=near.candidate_id + "_opposite",
        orientation=_opposite(near.orientation),
        supporting_slice_ids=(8801, 8802, 8803),
        supporting_frame_ids=(
            "opposite-frame-1",
            "opposite-frame-2",
            "opposite-frame-3",
        ),
        mean_dt=-near.mean_dt,
    )
    ingest_temporal_evidence_candidate(memory, opposite)

    resolution = resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(("world_i1", "s_intensity", "i1"),),
    )

    assert resolution.resolved is False
    assert resolution.ambiguous is True
    assert resolution.resolved_candidate is None
    assert resolution.reason == "contested-supported-world-continuation"
    assert len(resolution.matches) == 1
    assert resolution.matches[0].contested is True


def test_life_gate_011_prediction_assistance_is_read_only_and_separate_from_causal_memory():
    _engine, candidates = _selector_candidates((441, 442, 443))
    memory = _memory_from_candidates(candidates)
    temporal_before = memory.snapshot()

    causal_gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )
    causal_before = causal_gym.memory.snapshot()
    regimes_before = causal_gym.regimes

    resolution = resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(
            ("world_i1", "s_intensity", "i1"),
            ("world_i0", "s_intensity", "i0"),
        ),
    )

    assert resolution.resolved is True
    assert memory.snapshot() == temporal_before
    assert causal_gym.memory.snapshot() == causal_before == ()
    assert causal_gym.regimes == regimes_before


def test_life_gate_011_candidate_set_is_not_expanded_by_memory():
    _engine, candidates = _selector_candidates((451, 452, 453, 454))
    memory = _memory_from_candidates(candidates)

    resolution = resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(("only_world_i1", "s_intensity", "i1"),),
    )

    assert tuple(candidate.candidate_id for candidate in resolution.candidates) == (
        "only_world_i1",
    )
    assert tuple(item.candidate.candidate_id for item in resolution.matches) == (
        "only_world_i1",
    )
    assert resolution.resolved_candidate is not None
    assert resolution.resolved_candidate.candidate_id == "only_world_i1"


def test_life_gate_011_is_deterministic():
    _engine_a, candidates_a = _selector_candidates((461, 462, 463))
    _engine_b, candidates_b = _selector_candidates((461, 462, 463))
    assert candidates_a == candidates_b

    memory_a = _memory_from_candidates(candidates_a)
    memory_b = _memory_from_candidates(candidates_b)

    args = dict(
        current_sensor_id="s_intensity",
        current_band_id="i2",
        candidates=(
            ("world_i1", "s_intensity", "i1"),
            ("world_i0", "s_intensity", "i0"),
        ),
    )
    assert resolve_sensor_temporal_world_candidates(memory_a, **args) == (
        resolve_sensor_temporal_world_candidates(memory_b, **args)
    )
