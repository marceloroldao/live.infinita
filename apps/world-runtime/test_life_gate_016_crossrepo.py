from __future__ import annotations

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from memoria_resolutiva.structural_temporal_recall_v2 import (
    recall_structural_temporal_neighbors,
)
from reality_slice import TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_context_runtime import apply_environmental_context_constraints
from environmental_influence_agent_runtime import advance_environmental_influence_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_016 import build_life_gate_016_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


FLOW_SENSOR = "s_flow"
AGENT_SENSOR = "s_agent_signal_01"
CONTEXT_SENSOR = "s_context_signal_01"


def _episode(episode_id: int, context_state_id: str):
    world = build_life_gate_016_world(
        episode_id=episode_id,
        context_state_id=context_state_id,
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

    influence = advance_environmental_influence_agents(world, ticks=1)[0]
    constrained = apply_environmental_context_constraints(influence.world)
    physical = advance_distributed_environmental_agents(
        constrained.world,
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


def _learn(clear_ids=(), blocked_ids=()):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in clear_ids:
        world, window = _episode(episode_id, "ctx_clear")
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    for episode_id in blocked_ids:
        world, window = _episode(episode_id, "ctx_blocked")
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    memory = StructuralTemporalObservationMemory()
    decisions = ()
    if last_world is not None:
        decisions = select_temporal_evidence_candidates(
            engine,
            policy_from_world(last_world),
            provenance_by_slice=provenance,
        )
        for candidate in admitted_candidates(decisions):
            ingest_temporal_evidence_candidate(memory, candidate)
    return last_world, engine, decisions, memory


def _key(a: int, b: int):
    return (a, b) if a < b else (b, a)


def _decision(decisions, a: int, b: int):
    key = _key(a, b)
    return next(
        item
        for item in decisions
        if (item.pattern_a, item.pattern_b) == key
    )


def _address(pattern_id: int) -> str:
    return f"temporal:pattern:{pattern_id}"


def test_life_gate_016_same_agent_signal_has_two_physical_consequences_by_context():
    clear_world, clear_window = _episode(1001, "ctx_clear")
    blocked_world, blocked_window = _episode(1002, "ctx_blocked")

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    clear_patterns = {item.pattern for item in clear_window.reality_slice.occurrences}
    blocked_patterns = {item.pattern for item in blocked_window.reality_slice.occurrences}

    assert a0 in clear_patterns
    assert a0 in blocked_patterns
    assert c0 in clear_patterns
    assert c1 in blocked_patterns
    assert d1 in clear_patterns
    assert d2 in blocked_patterns
    assert clear_world["entities"]["wind_01"]["components"]["environmental_state"]["last_action_id"] == "wind_open_channel"
    assert blocked_world["entities"]["wind_01"]["components"]["environmental_state"]["last_action_id"] == "wind_open_channel"


def test_life_gate_016_uncontextualized_agent_pairs_fail_directional_reliability():
    _world, engine, decisions, _memory = _learn(
        clear_ids=(1011, 1012, 1013, 1014),
        blocked_ids=(1015, 1016, 1017, 1018),
    )

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    link_d1 = engine.links[_key(a0, d1)]
    link_d2 = engine.links[_key(a0, d2)]
    decision_d1 = _decision(decisions, a0, d1)
    decision_d2 = _decision(decisions, a0, d2)

    assert link_d1.repetitions == 4
    assert link_d2.repetitions == 4
    assert 0.49 < engine.directional_reliability(link_d1) < 0.51
    assert 0.49 < engine.directional_reliability(link_d2) < 0.51

    assert decision_d1.admitted is False
    assert decision_d2.admitted is False
    assert "insufficient-directional-reliability" in decision_d1.rejection_reasons
    assert "insufficient-directional-reliability" in decision_d2.rejection_reasons


def test_life_gate_016_context_specific_pairs_remain_reliable_and_are_admitted():
    _world, engine, decisions, _memory = _learn(
        clear_ids=(1021, 1022, 1023, 1024),
        blocked_ids=(1025, 1026, 1027, 1028),
    )

    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    clear_link = engine.links[_key(c0, d1)]
    blocked_link = engine.links[_key(c1, d2)]

    assert clear_link.repetitions == 4
    assert blocked_link.repetitions == 4
    assert engine.directional_reliability(clear_link) > 0.99
    assert engine.directional_reliability(blocked_link) > 0.99

    assert _decision(decisions, c0, d1).admitted is True
    assert _decision(decisions, c1, d2).admitted is True

    assert _key(c0, d2) not in engine.links
    assert _key(c1, d1) not in engine.links


def test_life_gate_016_memoria_does_not_promote_a0_to_universal_water_rule():
    _world, _engine, _decisions, memory = _learn(
        clear_ids=(1031, 1032, 1033, 1034),
        blocked_ids=(1035, 1036, 1037, 1038),
    )

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

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
    assert _address(d2) not in after


def test_life_gate_016_memoria_recalls_context_specific_consequences():
    _world, _engine, _decisions, memory = _learn(
        clear_ids=(1041, 1042, 1043, 1044),
        blocked_ids=(1045, 1046, 1047, 1048),
    )

    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    clear_recall = recall_structural_temporal_neighbors(
        memory,
        _address(c0),
        min_independent_slices=3,
    )
    blocked_recall = recall_structural_temporal_neighbors(
        memory,
        _address(c1),
        min_independent_slices=3,
    )

    clear_after = {
        item.pattern_address
        for item in clear_recall.neighbors
        if item.relation_to_query == "after_query"
    }
    blocked_after = {
        item.pattern_address
        for item in blocked_recall.neighbors
        if item.relation_to_query == "after_query"
    }

    assert _address(d1) in clear_after
    assert _address(d2) not in clear_after
    assert _address(d2) in blocked_after
    assert _address(d1) not in blocked_after


def test_life_gate_016_context_is_structural_not_semantic_in_memoria():
    _world, _engine, decisions, memory = _learn(
        clear_ids=(1051, 1052, 1053, 1054),
        blocked_ids=(1055, 1056, 1057, 1058),
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
        "wind",
        "water",
        "flow",
        "cause",
        "causes",
        "universal",
    ):
        assert forbidden not in serialized


def test_life_gate_016_directional_reliability_is_audit_visible():
    _world, _engine, decisions, _memory = _learn(
        clear_ids=(1061, 1062, 1063, 1064),
        blocked_ids=(1065, 1066, 1067, 1068),
    )

    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    candidate = _decision(decisions, c0, d1).candidate

    assert candidate is not None
    assert candidate.directional_reliability > 0.99
    payload = candidate.to_payload()
    assert payload["evidence"]["directional_reliability"] > 0.99


def test_life_gate_016_is_deterministic():
    a = _learn(
        clear_ids=(1071, 1072, 1073, 1074),
        blocked_ids=(1075, 1076, 1077, 1078),
    )
    b = _learn(
        clear_ids=(1071, 1072, 1073, 1074),
        blocked_ids=(1075, 1076, 1077, 1078),
    )

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
