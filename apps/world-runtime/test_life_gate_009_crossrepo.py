from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
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


def _trajectory(episode_id: int):
    world = build_life_gate_009_world(episode_id=episode_id)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    return world, reality_window_from_world_rule(world, observer_id="nova")


def _build_selector_state():
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in (101, 102, 103):
        world, window = _trajectory(episode_id)
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    return last_world, engine, decisions


def test_life_gate_009_admitted_candidate_is_presemantic_transport_only():
    _world, _engine, decisions = _build_selector_state()
    candidates = admitted_candidates(decisions)

    assert candidates

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    key = (i2, i1) if i2 < i1 else (i1, i2)
    candidate = next(
        item for item in candidates
        if (item.pattern_a, item.pattern_b) == key
    )

    payload = candidate.to_payload()
    serialized = repr(payload).lower()

    assert payload["candidate_id"].startswith("tec_")
    assert payload["pattern_addresses"] == (
        f"temporal:pattern:{candidate.pattern_a}",
        f"temporal:pattern:{candidate.pattern_b}",
    )
    assert payload["provenance"]["slice_ids"] == candidate.supporting_slice_ids
    assert payload["provenance"]["frame_ids"] == candidate.supporting_frame_ids

    for forbidden in (
        "water",
        "flow",
        "intensity",
        "sensor_id",
        "causes",
        "cause",
        "means",
        "semantic",
    ):
        assert forbidden not in serialized


def test_life_gate_009_selection_does_not_write_memoria():
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )
    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes

    _world, _engine, decisions = _build_selector_state()
    candidates = admitted_candidates(decisions)

    assert candidates
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before


def test_life_gate_009_selector_does_not_mutate_world():
    world, window = _trajectory(201)
    engine = TemporalAssociator(lambda0=0.0)
    engine.ingest(window.reality_slice)

    before = repr(world)
    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(world),
        provenance_by_slice={window.reality_slice.slice_id: window.frame_ids},
    )

    assert decisions
    assert repr(world) == before


def test_life_gate_009_far_relation_remains_rejected_while_near_relation_is_admitted():
    _world, engine, decisions = _build_selector_state()

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    i0 = sensor_pattern_id("s_intensity", "i0")

    near_key = (i2, i1) if i2 < i1 else (i1, i2)
    far_key = (i2, i0) if i2 < i0 else (i0, i2)

    near = next(
        item for item in decisions
        if (item.pattern_a, item.pattern_b) == near_key
    )
    far = next(
        item for item in decisions
        if (item.pattern_a, item.pattern_b) == far_key
    )

    assert near.admitted is True
    assert near.candidate is not None
    assert far.admitted is False
    assert far.candidate is None
    assert "insufficient-rho" in far.rejection_reasons

    assert engine.links[near_key].repetitions == engine.links[far_key].repetitions == 3
    assert engine.links[near_key].rho > engine.links[far_key].rho


def test_life_gate_009_is_deterministic():
    world_a, engine_a, decisions_a = _build_selector_state()
    world_b, engine_b, decisions_b = _build_selector_state()

    assert world_a["rules"]["temporal_evidence_selector"] == world_b["rules"]["temporal_evidence_selector"]
    assert decisions_a == decisions_b

    sig_a = tuple(
        sorted((key, link.rho, link.repetitions) for key, link in engine_a.links.items())
    )
    sig_b = tuple(
        sorted((key, link.rho, link.repetitions) for key, link in engine_b.links.items())
    )
    assert sig_a == sig_b
