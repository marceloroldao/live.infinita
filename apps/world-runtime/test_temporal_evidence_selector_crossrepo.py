from __future__ import annotations

from reality_slice import Modality, Occurrence, RealitySlice, TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_009 import build_life_gate_009_world
from temporal_evidence_selector import (
    TemporalEvidencePolicy,
    evaluate_temporal_association,
    policy_from_world,
    select_temporal_evidence_candidates,
)


def _key(a: int, b: int):
    return (a, b) if a < b else (b, a)


def _trajectory(episode_id: int):
    world = build_life_gate_009_world(episode_id=episode_id)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    window = reality_window_from_world_rule(world, observer_id="nova")
    return world, window


def _decision_for(decisions, a: int, b: int):
    key = _key(a, b)
    return next(
        item for item in decisions
        if (item.pattern_a, item.pattern_b) == key
    )


def test_selector_rejects_one_shot_temporal_link():
    world, window = _trajectory(1)
    engine = TemporalAssociator(lambda0=0.0)
    engine.ingest(window.reality_slice)

    policy = policy_from_world(world)
    decisions = select_temporal_evidence_candidates(
        engine,
        policy,
        provenance_by_slice={window.reality_slice.slice_id: window.frame_ids},
    )

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    decision = _decision_for(decisions, i2, i1)

    assert decision.admitted is False
    assert decision.candidate is None
    assert "insufficient-repetitions" in decision.rejection_reasons
    assert "insufficient-independent-slices" in decision.rejection_reasons
    assert "insufficient-rho" in decision.rejection_reasons
    assert "insufficient-evidence-score" in decision.rejection_reasons


def test_selector_distinguishes_near_and_far_links_with_equal_repetition():
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in (10, 11, 12):
        world, window = _trajectory(episode_id)
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    assert last_world is not None
    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    i0 = sensor_pattern_id("s_intensity", "i0")

    near = _decision_for(decisions, i2, i1)
    far = _decision_for(decisions, i2, i0)

    assert engine.links[_key(i2, i1)].repetitions == 3
    assert engine.links[_key(i2, i0)].repetitions == 3

    assert near.admitted is True
    assert near.candidate is not None
    assert far.admitted is False
    assert far.candidate is None
    assert "insufficient-rho" in far.rejection_reasons

    assert engine.links[_key(i2, i1)].rho > engine.links[_key(i2, i0)].rho


def test_selector_candidate_preserves_independent_slice_and_frame_provenance():
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in (20, 21, 22):
        world, window = _trajectory(episode_id)
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    candidate = _decision_for(decisions, i2, i1).candidate

    assert candidate is not None
    assert candidate.repetitions == 3
    assert len(candidate.supporting_slice_ids) == 3
    assert len(set(candidate.supporting_slice_ids)) == 3
    assert len(candidate.supporting_frame_ids) == 9
    assert len(set(candidate.supporting_frame_ids)) == 9


def test_selector_rejects_low_selectivity_coincidence():
    engine = TemporalAssociator(lambda0=0.0)
    sid = 1

    def ingest(patterns):
        nonlocal sid
        occurrences = tuple(
            Occurrence(
                pattern=pattern,
                modality=Modality.SENSOR,
                t_start=0.0,
                t_end=0.02,
                source=pattern,
                provenance=sid,
            )
            for pattern in patterns
        )
        engine.ingest(
            RealitySlice(
                slice_id=sid,
                t_start=0.0,
                t_end=0.02,
                occurrences=occurrences,
                provenance=(sid,),
            )
        )
        sid += 1

    for _ in range(10):
        ingest((101,))
    for _ in range(10):
        ingest((202,))
    for _ in range(3):
        ingest((101, 202))

    link = engine.links[(101, 202)]
    policy = TemporalEvidencePolicy(
        min_repetitions=3,
        min_independent_slices=3,
        min_rho=0.0,
        min_selectivity=0.80,
        min_temporal_stability=0.0,
        min_evidence_score=0.0,
        min_direction_confidence=0.0,
    )
    decision = evaluate_temporal_association(engine, link, policy)

    assert link.repetitions == 3
    assert engine.selectivity(link) < 0.80
    assert decision.admitted is False
    assert "insufficient-selectivity" in decision.rejection_reasons


def test_selector_rejects_temporally_unstable_relation():
    engine = TemporalAssociator(
        lambda0=0.0,
        simultaneous_delta=0.01,
        default_tau=2.0,
    )

    for sid, dt in enumerate((0.1, 0.5, 1.0), start=1):
        engine.ingest(
            RealitySlice(
                slice_id=sid,
                t_start=0.0,
                t_end=1.2,
                occurrences=(
                    Occurrence(301, Modality.SENSOR, 0.0, 0.02, 1, sid),
                    Occurrence(302, Modality.SENSOR, dt, dt + 0.02, 2, sid),
                ),
                provenance=(sid,),
            )
        )

    link = engine.links[(301, 302)]
    policy = TemporalEvidencePolicy(
        min_repetitions=3,
        min_independent_slices=3,
        min_rho=0.0,
        min_selectivity=0.0,
        min_temporal_stability=0.90,
        min_evidence_score=0.0,
        min_direction_confidence=0.0,
    )
    decision = evaluate_temporal_association(engine, link, policy)

    assert engine.temporal_stability(link) < 0.90
    assert decision.admitted is False
    assert "insufficient-temporal-stability" in decision.rejection_reasons


def test_selector_rejects_inconsistent_temporal_direction():
    engine = TemporalAssociator(
        lambda0=0.0,
        simultaneous_delta=0.01,
        default_tau=1.0,
    )

    for sid in range(1, 5):
        if sid % 2:
            occurrences = (
                Occurrence(401, Modality.SENSOR, 0.0, 0.02, 1, sid),
                Occurrence(402, Modality.SENSOR, 0.2, 0.22, 2, sid),
            )
        else:
            occurrences = (
                Occurrence(402, Modality.SENSOR, 0.0, 0.02, 2, sid),
                Occurrence(401, Modality.SENSOR, 0.2, 0.22, 1, sid),
            )
        engine.ingest(
            RealitySlice(
                slice_id=sid,
                t_start=0.0,
                t_end=0.25,
                occurrences=occurrences,
                provenance=(sid,),
            )
        )

    link = engine.links[(401, 402)]
    policy = TemporalEvidencePolicy(
        min_repetitions=4,
        min_independent_slices=4,
        min_rho=0.0,
        min_selectivity=0.0,
        min_temporal_stability=0.0,
        min_evidence_score=0.0,
        min_direction_confidence=0.80,
    )
    decision = evaluate_temporal_association(engine, link, policy)

    assert max(link.direction_probabilities()) < 0.80
    assert decision.admitted is False
    assert "insufficient-direction-confidence" in decision.rejection_reasons
