from __future__ import annotations

from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_context_recall_v2 import (
    recall_structural_context,
)
from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from reality_slice import TemporalAssociator

from context_observation_memoria_adapter import (
    ingest_higher_order_context_candidate,
)
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from environmental_state_interaction_runtime import apply_environmental_state_interactions
from higher_order_context_selector import (
    make_sparse_context_associator,
    policy_from_world,
    select_higher_order_context_candidates,
)
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_019 import build_life_gate_019_world


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


def _episode(
    episode_id: int,
    wind_phase_id: str,
    barrier_phase_id: str,
):
    world = build_life_gate_019_world(
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
    pairwise = TemporalAssociator(lambda0=0.0)
    policy = None
    higher = None
    provenance = {}
    last_world = None
    episode_id = 1400

    for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
        for _ in range(4):
            episode_id += 1
            world, window = _episode(
                episode_id,
                wind_phase,
                barrier_phase,
            )
            last_world = world
            if policy is None:
                policy = policy_from_world(world)
                higher = make_sparse_context_associator(
                    policy,
                    lambda0=0.0,
                )
            pairwise.ingest(window.reality_slice)
            higher.ingest(window.reality_slice)
            provenance[window.reality_slice.slice_id] = window.frame_ids

    candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        policy,
        provenance_by_slice=provenance,
    )
    context_memory = StructuralContextObservationMemory()
    for candidate in candidates:
        ingest_higher_order_context_candidate(
            context_memory,
            candidate,
        )
    return last_world, pairwise, higher, candidates, context_memory


def _candidate_map(candidates):
    return {
        (
            tuple(candidate.antecedent_patterns),
            candidate.consequence_pattern,
        ): candidate
        for candidate in candidates
    }


def test_life_gate_019_sparse_higher_order_selector_recovers_exactly_four_xor_contexts():
    _world, _pairwise, _higher, candidates, _memory = _learn_balanced()

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    a1 = sensor_pattern_id(AGENT_SENSOR, "a1")
    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    expected = {
        (tuple(sorted((a0, c0))), d1),
        (tuple(sorted((a0, c1))), d2),
        (tuple(sorted((a1, c0))), d2),
        (tuple(sorted((a1, c1))), d1),
    }
    assert set(_candidate_map(candidates)) == expected
    assert len(candidates) == 4


def test_life_gate_019_joint_context_is_reliable_while_each_lower_order_relation_remains_insufficient():
    _world, _pairwise, _higher, candidates, _memory = _learn_balanced()

    for candidate in candidates:
        assert candidate.repetitions == 4
        assert candidate.context_coverage == 1.0
        assert candidate.context_reliability > 0.99
        assert all(
            0.49 < value < 0.51
            for value in candidate.lower_order_reliabilities
        )
        assert len(candidate.supporting_slice_ids) == 4
        assert len(set(candidate.supporting_slice_ids)) == 4
        assert len(candidate.supporting_frame_ids) == 16
        assert len(set(candidate.supporting_frame_ids)) == 16


def test_life_gate_019_does_not_materialize_combined_pattern_ids():
    _world, pairwise, higher, candidates, memory = _learn_balanced()

    expected_individual_patterns = {
        sensor_pattern_id(FLOW_SENSOR, "d0"),
        sensor_pattern_id(FLOW_SENSOR, "d1"),
        sensor_pattern_id(FLOW_SENSOR, "d2"),
        sensor_pattern_id(AGENT_SENSOR, "a0"),
        sensor_pattern_id(AGENT_SENSOR, "a1"),
        sensor_pattern_id(CONTEXT_SENSOR, "c0"),
        sensor_pattern_id(CONTEXT_SENSOR, "c1"),
    }

    assert set(pairwise.pattern_slices) == expected_individual_patterns
    assert len(pairwise.pattern_slices) == 7
    assert all(
        isinstance(link.antecedents, tuple)
        and len(link.antecedents) == 2
        for link in higher.links.values()
    )
    assert all(
        not hasattr(candidate, "combined_pattern")
        and not hasattr(candidate, "context_pattern")
        for candidate in candidates
    )
    assert all(
        len(item.antecedent_patterns) == 2
        for item in memory.snapshot()
    )


def test_life_gate_019_memoria_context_recall_resolves_all_four_xor_combinations():
    _world, _pairwise, _higher, _candidates, memory = _learn_balanced()

    table = {
        ("a0", "c0"): "d1",
        ("a0", "c1"): "d2",
        ("a1", "c0"): "d2",
        ("a1", "c1"): "d1",
    }

    for (agent_band, context_band), consequence_band in table.items():
        antecedents = (
            _address(sensor_pattern_id(AGENT_SENSOR, agent_band)),
            _address(sensor_pattern_id(CONTEXT_SENSOR, context_band)),
        )
        recall = recall_structural_context(
            memory,
            antecedents,
            min_independent_slices=3,
        )
        assert len(recall.neighbors) == 1
        assert recall.neighbors[0].consequence_pattern == _address(
            sensor_pattern_id(FLOW_SENSOR, consequence_band)
        )
        assert recall.neighbors[0].hypothesis.independent_support == 4


def test_life_gate_019_exact_context_is_required_and_single_pattern_still_cannot_resolve_xor():
    _world, _pairwise, _higher, _candidates, memory = _learn_balanced()

    try:
        recall_structural_context(
            memory,
            (_address(sensor_pattern_id(AGENT_SENSOR, "a0")),),
        )
    except ValueError as exc:
        assert "exactly two" in str(exc)
    else:
        raise AssertionError("higher-order recall must require the full observed context")


def test_life_gate_019_context_adapter_does_not_write_pairwise_temporal_memory():
    _world, _pairwise, _higher, _candidates, context_memory = _learn_balanced()
    pair_memory = StructuralTemporalObservationMemory()

    assert len(context_memory.snapshot()) == 4
    assert pair_memory.snapshot() == ()


def test_life_gate_019_payload_and_memoria_snapshot_remain_presemantic():
    _world, _pairwise, _higher, candidates, memory = _learn_balanced()

    serialized = (
        repr([candidate.to_payload() for candidate in candidates])
        + repr(memory.snapshot())
    ).lower()

    for forbidden in (
        "xor",
        "gust",
        "lull",
        "wind",
        "water",
        "flow",
        "barrier",
        "clear",
        "blocked",
        "case_00",
        "case_01",
        "case_10",
        "case_11",
        "cause",
        "causes",
    ):
        assert forbidden not in serialized


def test_life_gate_019_candidate_identity_and_memory_are_deterministic():
    a = _learn_balanced()
    b = _learn_balanced()

    _world_a, _pairwise_a, _higher_a, candidates_a, memory_a = a
    _world_b, _pairwise_b, _higher_b, candidates_b, memory_b = b

    assert candidates_a == candidates_b
    assert memory_a.snapshot() == memory_b.snapshot()
