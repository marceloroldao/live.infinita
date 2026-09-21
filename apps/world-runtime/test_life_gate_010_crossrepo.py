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


def _episode(episode_id: int):
    world = build_life_gate_009_world(episode_id=episode_id)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    return world, reality_window_from_world_rule(world, observer_id="nova")


def _selector_state(episode_ids):
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
    return last_world, engine, decisions


def _near_candidate(episode_ids=(301, 302, 303)):
    _world, _engine, decisions = _selector_state(episode_ids)
    candidates = admitted_candidates(decisions)

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    key = (i2, i1) if i2 < i1 else (i1, i2)

    return next(
        candidate
        for candidate in candidates
        if (candidate.pattern_a, candidate.pattern_b) == key
    )


def _addresses(candidate):
    return (
        f"temporal:pattern:{candidate.pattern_a}",
        f"temporal:pattern:{candidate.pattern_b}",
    )


def _opposite(orientation: str) -> str:
    return {
        "a_before_b": "b_before_a",
        "b_before_a": "a_before_b",
        "simultaneous": "simultaneous",
    }[orientation]


def test_life_gate_010_admitted_candidate_enters_separate_temporal_observation_memory():
    candidate = _near_candidate()
    memory = StructuralTemporalObservationMemory()
    causal_gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    causal_before = causal_gym.memory.snapshot()
    regimes_before = causal_gym.regimes

    observation = ingest_temporal_evidence_candidate(memory, candidate)
    a, b = _addresses(candidate)
    resolution = memory.resolve(a, b, min_independent_slices=3)

    assert len(memory.snapshot()) == 1
    assert observation.source_candidate_id == candidate.candidate_id
    assert observation.supporting_slice_ids == tuple(
        sorted(str(item) for item in candidate.supporting_slice_ids)
    )
    assert observation.supporting_frame_ids == tuple(
        sorted(candidate.supporting_frame_ids)
    )

    assert resolution.resolved is True
    assert resolution.ambiguous is False
    assert resolution.supported_orientation == observation.orientation
    assert resolution.reason == "single-supported-orientation"
    assert resolution.hypotheses[0].independent_support == 3

    # Passive temporal structure remains completely separate from causal episodes.
    assert causal_gym.memory.snapshot() == causal_before == ()
    assert causal_gym.regimes == regimes_before


def test_life_gate_010_exact_candidate_replay_is_idempotent():
    candidate = _near_candidate()
    memory = StructuralTemporalObservationMemory()

    first = ingest_temporal_evidence_candidate(memory, candidate)
    second = ingest_temporal_evidence_candidate(memory, candidate)

    assert first is second
    assert len(memory.snapshot()) == 1


def test_life_gate_010_expanded_candidate_adds_only_new_independent_slice_support():
    first_candidate = _near_candidate((311, 312, 313))
    expanded_candidate = _near_candidate((311, 312, 313, 314))

    memory = StructuralTemporalObservationMemory()
    first = ingest_temporal_evidence_candidate(memory, first_candidate)
    second = ingest_temporal_evidence_candidate(memory, expanded_candidate)

    assert first.source_candidate_id == second.source_candidate_id
    assert first.observation_id != second.observation_id
    assert len(memory.snapshot()) == 2

    a, b = _addresses(expanded_candidate)
    resolution = memory.resolve(a, b, min_independent_slices=4)
    hypothesis = next(item for item in resolution.hypotheses if item.supported)

    assert hypothesis.independent_support == 4
    assert len(hypothesis.supporting_slice_ids) == 4
    assert resolution.resolved is True


def test_life_gate_010_weak_competitor_is_preserved_but_does_not_replace_supported_orientation():
    candidate = _near_candidate((321, 322, 323))
    memory = StructuralTemporalObservationMemory()
    supported = ingest_temporal_evidence_candidate(memory, candidate)

    opposite = replace(
        candidate,
        candidate_id=candidate.candidate_id + "_weak_opposite",
        orientation=_opposite(candidate.orientation),
        supporting_slice_ids=(9901,),
        supporting_frame_ids=("opposite-frame-1",),
        mean_dt=-candidate.mean_dt,
    )
    weak = ingest_temporal_evidence_candidate(memory, opposite)

    a, b = _addresses(candidate)
    resolution = memory.resolve(a, b, min_independent_slices=3)

    assert weak.orientation != supported.orientation
    assert resolution.resolved is True
    assert resolution.ambiguous is False
    assert resolution.supported_orientation == supported.orientation
    assert len(resolution.hypotheses) == 2

    weak_hypothesis = next(
        item
        for item in resolution.hypotheses
        if item.orientation == weak.orientation
    )
    assert weak_hypothesis.supported is False
    assert weak_hypothesis.independent_support == 1


def test_life_gate_010_competing_supported_orientation_creates_ambiguity_without_deletion():
    candidate = _near_candidate((331, 332, 333))
    memory = StructuralTemporalObservationMemory()
    first = ingest_temporal_evidence_candidate(memory, candidate)

    opposite = replace(
        candidate,
        candidate_id=candidate.candidate_id + "_supported_opposite",
        orientation=_opposite(candidate.orientation),
        supporting_slice_ids=(9911, 9912, 9913),
        supporting_frame_ids=(
            "opposite-frame-1",
            "opposite-frame-2",
            "opposite-frame-3",
        ),
        mean_dt=-candidate.mean_dt,
    )
    second = ingest_temporal_evidence_candidate(memory, opposite)

    a, b = _addresses(candidate)
    resolution = memory.resolve(a, b, min_independent_slices=3)

    assert first.orientation != second.orientation
    assert len(memory.snapshot()) == 2
    assert resolution.resolved is False
    assert resolution.ambiguous is True
    assert resolution.supported_orientation is None
    assert resolution.reason == "competing-supported-orientations"
    assert {item.orientation for item in resolution.hypotheses} == {
        first.orientation,
        second.orientation,
    }
    assert all(item.supported for item in resolution.hypotheses)
    assert all(item.independent_support == 3 for item in resolution.hypotheses)


def test_life_gate_010_observation_preserves_evidence_for_audit_without_semantic_promotion():
    candidate = _near_candidate((341, 342, 343))
    memory = StructuralTemporalObservationMemory()

    observation = ingest_temporal_evidence_candidate(memory, candidate)
    serialized = repr(observation).lower()

    assert observation.rho == candidate.rho
    assert observation.selectivity == candidate.selectivity
    assert observation.temporal_stability == candidate.temporal_stability
    assert observation.evidence_score == candidate.evidence_score
    assert observation.orientation_confidence == candidate.orientation_confidence
    assert observation.mean_dt == candidate.mean_dt
    assert observation.variance_dt == candidate.variance_dt

    for forbidden in (
        "water",
        "flow",
        "intensity",
        "causes",
        "cause",
        "fact",
        "truth",
        "law",
    ):
        assert forbidden not in serialized


def test_life_gate_010_is_deterministic():
    candidate_a = _near_candidate((351, 352, 353))
    candidate_b = _near_candidate((351, 352, 353))
    assert candidate_a == candidate_b

    memory_a = StructuralTemporalObservationMemory()
    memory_b = StructuralTemporalObservationMemory()

    ingest_temporal_evidence_candidate(memory_a, candidate_a)
    ingest_temporal_evidence_candidate(memory_b, candidate_b)

    a, b = _addresses(candidate_a)
    assert memory_a.snapshot() == memory_b.snapshot()
    assert memory_a.resolve(a, b) == memory_b.resolve(a, b)
