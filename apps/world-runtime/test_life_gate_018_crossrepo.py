from __future__ import annotations

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from memoria_resolutiva.structural_temporal_recall_v2 import (
    recall_structural_temporal_neighbors,
)
from reality_slice import TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from environmental_state_interaction_runtime import apply_environmental_state_interactions
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_018 import build_life_gate_018_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


FLOW_SENSOR = "s_flow"
AGENT_SENSOR = "s_agent_signal_01"
CONTEXT_SENSOR = "s_context_signal_01"

COMBINATIONS = (
    ("w_gust_a", "b_clear", "a0", "c0", "d1"),
    ("w_gust_a", "b_blocked", "a0", "c1", "d2"),
    ("w_lull_a", "b_clear", "a1", "c0", "d2"),
    ("w_lull_a", "b_blocked", "a1", "c1", "d1"),
)


def _address(pattern_id: int) -> str:
    return f"temporal:pattern:{pattern_id}"


def _key(a: int, b: int):
    return (a, b) if a < b else (b, a)


def _decision(decisions, a: int, b: int):
    key = _key(a, b)
    return next(
        item
        for item in decisions
        if (item.pattern_a, item.pattern_b) == key
    )


def _episode(
    episode_id: int,
    wind_phase_id: str,
    barrier_phase_id: str,
):
    world = build_life_gate_018_world(
        episode_id=episode_id,
        wind_phase_id=wind_phase_id,
        barrier_phase_id=barrier_phase_id,
    )

    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(FLOW_SENSOR,),
    ).world
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(AGENT_SENSOR,),
    ).world
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(CONTEXT_SENSOR,),
    ).world

    interacted = apply_environmental_state_interactions(world)
    physical = advance_distributed_environmental_agents(
        interacted.world,
        ticks=1,
    )[0]
    world = sample_multimodal_sensor_frame(
        physical.world,
        observer_id="nova",
        sensor_ids=(FLOW_SENSOR,),
    ).world

    return world, reality_window_from_world_rule(
        world,
        observer_id="nova",
    )


def _learn_balanced():
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None
    episode_id = 1200

    for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
        for _ in range(4):
            episode_id += 1
            world, window = _episode(
                episode_id,
                wind_phase,
                barrier_phase,
            )
            last_world = world
            engine.ingest(window.reality_slice)
            provenance[window.reality_slice.slice_id] = window.frame_ids

    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    memory = StructuralTemporalObservationMemory()
    for candidate in admitted_candidates(decisions):
        ingest_temporal_evidence_candidate(memory, candidate)
    return last_world, engine, decisions, memory


def test_life_gate_018_four_physical_combinations_have_deterministic_xor_outcomes():
    observed = {}
    episode_id = 1300
    for wind_phase, barrier_phase, agent_band, context_band, consequence in COMBINATIONS:
        episode_id += 1
        _world, window = _episode(
            episode_id,
            wind_phase,
            barrier_phase,
        )
        patterns = {item.pattern for item in window.reality_slice.occurrences}
        assert sensor_pattern_id(AGENT_SENSOR, agent_band) in patterns
        assert sensor_pattern_id(CONTEXT_SENSOR, context_band) in patterns
        assert sensor_pattern_id(FLOW_SENSOR, consequence) in patterns
        observed[(agent_band, context_band)] = consequence

    assert observed == {
        ("a0", "c0"): "d1",
        ("a0", "c1"): "d2",
        ("a1", "c0"): "d2",
        ("a1", "c1"): "d1",
    }


def test_life_gate_018_every_single_signal_is_only_half_reliable_for_each_consequence():
    _world, engine, decisions, _memory = _learn_balanced()

    patterns = {
        "a0": sensor_pattern_id(AGENT_SENSOR, "a0"),
        "a1": sensor_pattern_id(AGENT_SENSOR, "a1"),
        "c0": sensor_pattern_id(CONTEXT_SENSOR, "c0"),
        "c1": sensor_pattern_id(CONTEXT_SENSOR, "c1"),
        "d1": sensor_pattern_id(FLOW_SENSOR, "d1"),
        "d2": sensor_pattern_id(FLOW_SENSOR, "d2"),
    }

    for antecedent in ("a0", "a1", "c0", "c1"):
        for consequence in ("d1", "d2"):
            link = engine.links[_key(patterns[antecedent], patterns[consequence])]
            decision = _decision(
                decisions,
                patterns[antecedent],
                patterns[consequence],
            )
            assert link.repetitions == 4
            assert 0.49 < engine.directional_reliability(link) < 0.51
            assert decision.admitted is False
            assert (
                "insufficient-directional-reliability"
                in decision.rejection_reasons
            )


def test_life_gate_018_pairwise_signal_context_links_also_cannot_encode_conjunction():
    _world, engine, decisions, _memory = _learn_balanced()

    patterns = {
        "a0": sensor_pattern_id(AGENT_SENSOR, "a0"),
        "a1": sensor_pattern_id(AGENT_SENSOR, "a1"),
        "c0": sensor_pattern_id(CONTEXT_SENSOR, "c0"),
        "c1": sensor_pattern_id(CONTEXT_SENSOR, "c1"),
    }

    for agent in ("a0", "a1"):
        for context in ("c0", "c1"):
            link = engine.links[_key(patterns[agent], patterns[context])]
            decision = _decision(decisions, patterns[agent], patterns[context])
            assert link.repetitions == 4
            assert 0.49 < engine.directional_reliability(link) < 0.51
            assert decision.admitted is False


def test_life_gate_018_bridge_creates_no_synthetic_conjunction_pattern():
    _world, engine, _decisions, _memory = _learn_balanced()

    expected_patterns = {
        sensor_pattern_id(FLOW_SENSOR, "d0"),
        sensor_pattern_id(FLOW_SENSOR, "d1"),
        sensor_pattern_id(FLOW_SENSOR, "d2"),
        sensor_pattern_id(AGENT_SENSOR, "a0"),
        sensor_pattern_id(AGENT_SENSOR, "a1"),
        sensor_pattern_id(CONTEXT_SENSOR, "c0"),
        sensor_pattern_id(CONTEXT_SENSOR, "c1"),
    }

    assert set(engine.pattern_slices) == expected_patterns
    assert len(engine.pattern_slices) == 7


def test_life_gate_018_memoria_cannot_resolve_xor_from_any_single_pairwise_query():
    _world, _engine, _decisions, memory = _learn_balanced()

    d1 = _address(sensor_pattern_id(FLOW_SENSOR, "d1"))
    d2 = _address(sensor_pattern_id(FLOW_SENSOR, "d2"))

    for sensor_id, band_id in (
        (AGENT_SENSOR, "a0"),
        (AGENT_SENSOR, "a1"),
        (CONTEXT_SENSOR, "c0"),
        (CONTEXT_SENSOR, "c1"),
    ):
        recall = recall_structural_temporal_neighbors(
            memory,
            _address(sensor_pattern_id(sensor_id, band_id)),
            min_independent_slices=3,
        )
        after = {
            item.pattern_address
            for item in recall.neighbors
            if item.relation_to_query == "after_query"
        }
        assert d1 not in after
        assert d2 not in after


def test_life_gate_018_physical_truth_is_deterministic_while_pairwise_cognition_remains_unresolved():
    _world_a, engine_a, decisions_a, memory_a = _learn_balanced()
    _world_b, engine_b, decisions_b, memory_b = _learn_balanced()

    assert decisions_a == decisions_b
    assert memory_a.snapshot() == memory_b.snapshot()
    assert tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                engine_a.directional_reliability(link),
            )
            for key, link in engine_a.links.items()
        )
    ) == tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                engine_b.directional_reliability(link),
            )
            for key, link in engine_b.links.items()
        )
    )


def test_life_gate_018_no_xor_semantics_enter_cognitive_payloads():
    _world, _engine, decisions, memory = _learn_balanced()

    payloads = [
        candidate.to_payload()
        for candidate in admitted_candidates(decisions)
    ]
    serialized = (repr(payloads) + repr(memory.snapshot())).lower()

    for forbidden in (
        "xor",
        "gust",
        "lull",
        "barrier",
        "clear",
        "blocked",
        "wind",
        "water",
        "flow",
        "case_00",
        "case_01",
        "case_10",
        "case_11",
        "cause",
        "causes",
    ):
        assert forbidden not in serialized
