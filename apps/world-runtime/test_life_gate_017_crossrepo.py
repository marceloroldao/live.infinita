from __future__ import annotations

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from memoria_resolutiva.structural_temporal_recall_v2 import (
    recall_structural_temporal_neighbors,
)
from reality_slice import TemporalAssociator

from contextual_multiagent_environment_runtime import (
    advance_contextual_multiagent_step,
)
from environmental_context_process_runtime import (
    advance_environmental_context_processes,
)
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import (
    reality_window_from_world,
    reality_window_from_world_rule,
    sensor_pattern_id,
)
from scenario_life_gate_017 import build_life_gate_017_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


FLOW_SENSOR = "s_flow"
AGENT_SENSOR = "s_agent_signal_01"
CONTEXT_SENSOR = "s_context_signal_01"


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


def _two_step_episode(episode_id: int):
    world = build_life_gate_017_world(episode_id=episode_id)

    # Step 1 starts from d0, a0, c0.
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

    first = advance_contextual_multiagent_step(
        world,
        observer_id="nova",
        sensor_ids=(FLOW_SENSOR,),
    )
    clear_window = reality_window_from_world_rule(
        first.world,
        observer_id="nova",
    )

    # The same world has now evolved to Wind gust_b and barrier blocked.
    world = sample_multimodal_sensor_frame(
        first.world,
        observer_id="nova",
        sensor_ids=(AGENT_SENSOR,),
    ).world
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(CONTEXT_SENSOR,),
    ).world

    second = advance_contextual_multiagent_step(
        world,
        observer_id="nova",
        sensor_ids=(FLOW_SENSOR,),
    )
    blocked_window = reality_window_from_world_rule(
        second.world,
        observer_id="nova",
    )
    return second.world, clear_window, blocked_window


def _learn_two_step_trajectories(episode_ids):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in episode_ids:
        world, clear_window, blocked_window = _two_step_episode(episode_id)
        last_world = world
        for window in (clear_window, blocked_window):
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


def _context_trajectory_episode(episode_id: int):
    world = build_life_gate_017_world(episode_id=episode_id)

    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(CONTEXT_SENSOR,),
    ).world
    world = advance_environmental_context_processes(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(CONTEXT_SENSOR,),
    ).world

    return world, reality_window_from_world(
        world,
        observer_id="nova",
        frame_count=2,
    )


def _learn_context_trajectory(episode_ids):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in episode_ids:
        world, window = _context_trajectory_episode(episode_id)
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


def test_life_gate_017_one_world_generates_clear_then_blocked_context_without_episode_selector():
    world, clear_window, blocked_window = _two_step_episode(1101)

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d0 = sensor_pattern_id(FLOW_SENSOR, "d0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    second_d0 = sensor_pattern_id(FLOW_SENSOR, "d0")

    clear_patterns = {item.pattern for item in clear_window.reality_slice.occurrences}
    blocked_patterns = {
        item.pattern for item in blocked_window.reality_slice.occurrences
    }

    assert clear_patterns == {d0, a0, c0, d1}
    assert blocked_patterns == {d1, a0, c1, second_d0}

    process_state = world["entities"]["barrier_01"]["components"]["process_state"]
    assert process_state["generation"] == 2
    assert process_state["phase_id"] == "b_clear"

    wind_state = world["entities"]["wind_01"]["components"]["environmental_state"]
    assert wind_state["generation"] == 2
    assert wind_state["phase_id"] == "w_lull_a"


def test_life_gate_017_same_a0_becomes_unreliable_across_evolving_context_trajectory():
    _world, engine, decisions, _memory = _learn_two_step_trajectories(
        (1111, 1112, 1113, 1114)
    )

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d0 = sensor_pattern_id(FLOW_SENSOR, "d0")

    decision_d1 = _decision(decisions, a0, d1)
    decision_d0 = _decision(decisions, a0, d0)

    assert decision_d1.admitted is False
    assert decision_d0.admitted is False
    assert engine.directional_reliability(
        engine.links[_key(a0, d1)]
    ) < 0.75
    assert engine.directional_reliability(
        engine.links[_key(a0, d0)]
    ) < 0.75

    assert (
        "insufficient-directional-reliability" in decision_d1.rejection_reasons
        or "insufficient-direction-confidence" in decision_d1.rejection_reasons
    )
    assert (
        "insufficient-directional-reliability" in decision_d0.rejection_reasons
        or "insufficient-direction-confidence" in decision_d0.rejection_reasons
    )


def test_life_gate_017_context_specific_future_relations_survive_evolving_process():
    _world, engine, decisions, _memory = _learn_two_step_trajectories(
        (1121, 1122, 1123, 1124)
    )

    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d0 = sensor_pattern_id(FLOW_SENSOR, "d0")

    clear = _decision(decisions, c0, d1)
    blocked = _decision(decisions, c1, d0)

    assert clear.admitted is True
    assert blocked.admitted is True
    assert engine.directional_reliability(
        engine.links[_key(c0, d1)]
    ) > 0.99
    assert engine.directional_reliability(
        engine.links[_key(c1, d0)]
    ) > 0.99


def test_life_gate_017_prior_consequence_is_preserved_as_before_query_not_false_future():
    _world, _engine, _decisions, memory = _learn_two_step_trajectories(
        (1131, 1132, 1133, 1134)
    )

    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d0 = sensor_pattern_id(FLOW_SENSOR, "d0")

    recall = recall_structural_temporal_neighbors(
        memory,
        _address(c1),
        min_independent_slices=3,
    )

    after = {
        item.pattern_address
        for item in recall.neighbors
        if item.relation_to_query == "after_query"
    }
    before = {
        item.pattern_address
        for item in recall.neighbors
        if item.relation_to_query == "before_query"
    }

    assert _address(d0) in after
    assert _address(d1) not in after
    # d1 may exist structurally before c1, but must not be promoted as its future.
    if _address(d1) in {
        item.pattern_address for item in recall.neighbors
    }:
        assert _address(d1) in before


def test_life_gate_017_memoria_still_does_not_promote_a0_to_universal_consequence():
    _world, _engine, _decisions, memory = _learn_two_step_trajectories(
        (1141, 1142, 1143, 1144)
    )

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d0 = sensor_pattern_id(FLOW_SENSOR, "d0")

    recall = recall_structural_temporal_neighbors(
        memory,
        _address(a0),
        min_independent_slices=3,
    )
    after = {
        item.pattern_address
        for item in recall.neighbors
        if item.relation_to_query == "after_query"
    }

    assert _address(d1) not in after
    assert _address(d0) not in after


def test_life_gate_017_context_trajectory_itself_is_learned_from_repetition():
    _world, engine, decisions, memory = _learn_context_trajectory(
        (1151, 1152, 1153, 1154)
    )

    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")

    link = engine.links[_key(c0, c1)]
    decision = _decision(decisions, c0, c1)

    assert link.repetitions == 4
    assert engine.directional_reliability(link) > 0.99
    assert decision.admitted is True

    recall = recall_structural_temporal_neighbors(
        memory,
        _address(c0),
        min_independent_slices=3,
    )
    after = {
        item.pattern_address
        for item in recall.neighbors
        if item.relation_to_query == "after_query"
    }
    assert _address(c1) in after


def test_life_gate_017_context_trajectory_uses_independent_slice_provenance():
    _world, _engine, decisions, _memory = _learn_context_trajectory(
        (1161, 1162, 1163, 1164)
    )

    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    candidate = _decision(decisions, c0, c1).candidate

    assert candidate is not None
    assert candidate.repetitions == 4
    assert len(candidate.supporting_slice_ids) == 4
    assert len(set(candidate.supporting_slice_ids)) == 4
    assert len(candidate.supporting_frame_ids) == 8
    assert len(set(candidate.supporting_frame_ids)) == 8


def test_life_gate_017_cognition_contains_no_process_semantics():
    _world, _engine, decisions, memory = _learn_two_step_trajectories(
        (1171, 1172, 1173, 1174)
    )

    payloads = [
        candidate.to_payload()
        for candidate in admitted_candidates(decisions)
    ]
    serialized = (repr(payloads) + repr(memory.snapshot())).lower()

    for forbidden in (
        "barrier",
        "clear",
        "blocked",
        "process",
        "wind",
        "water",
        "flow",
        "cause",
        "causes",
    ):
        assert forbidden not in serialized


def test_life_gate_017_is_deterministic():
    a = _learn_two_step_trajectories((1181, 1182, 1183, 1184))
    b = _learn_two_step_trajectories((1181, 1182, 1183, 1184))

    _world_a, engine_a, decisions_a, memory_a = a
    _world_b, engine_b, decisions_b, memory_b = b

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
