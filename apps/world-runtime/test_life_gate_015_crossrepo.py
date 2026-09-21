from __future__ import annotations

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from memoria_resolutiva.structural_temporal_recall_v2 import (
    recall_structural_temporal_neighbors,
)
from reality_slice import TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_influence_agent_runtime import advance_environmental_influence_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_015 import build_life_gate_015_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


SIGNAL_SENSOR = "s_agent_signal_01"
FLOW_SENSOR = "s_flow"


def _episode(
    episode_id: int,
    wind_phase_id: str,
    *,
    signal_after_consequence: bool = False,
):
    world = build_life_gate_015_world(
        episode_id=episode_id,
        wind_phase_id=wind_phase_id,
    )

    # Frame 0: Water state before the other agent acts.
    world = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=(FLOW_SENSOR,),
    ).world

    if not signal_after_consequence:
        # Frame 1: independent opaque agent signal before the physical consequence.
        world = sample_multimodal_sensor_frame(
            world,
            observer_id="nova",
            sensor_ids=(SIGNAL_SENSOR,),
        ).world

    influence = advance_environmental_influence_agents(world, ticks=1)[0]
    physical = advance_distributed_environmental_agents(
        influence.world,
        ticks=1,
    )[0]

    # Consequence frame: Water after the agent action.
    world = sample_multimodal_sensor_frame(
        physical.world,
        observer_id="nova",
        sensor_ids=(FLOW_SENSOR,),
    ).world

    if signal_after_consequence:
        # Adversarial timing: same agent state family is sampled after Water.
        world = sample_multimodal_sensor_frame(
            world,
            observer_id="nova",
            sensor_ids=(SIGNAL_SENSOR,),
        ).world

    window = reality_window_from_world_rule(
        world,
        observer_id="nova",
    )
    return world, window


def _learn(gust_ids=(), lull_ids=(), *, signal_after_consequence=False):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in gust_ids:
        world, window = _episode(
            episode_id,
            "w_gust_a",
            signal_after_consequence=signal_after_consequence,
        )
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    for episode_id in lull_ids:
        world, window = _episode(
            episode_id,
            "w_lull_a",
            signal_after_consequence=signal_after_consequence,
        )
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    decisions = ()
    memory = StructuralTemporalObservationMemory()
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


def test_life_gate_015_reality_slice_contains_separate_agent_and_water_patterns_in_order():
    _world, window = _episode(901, "w_gust_a")

    d0 = sensor_pattern_id(FLOW_SENSOR, "d0")
    a0 = sensor_pattern_id(SIGNAL_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")

    occurrences = window.reality_slice.occurrences
    by_pattern = {item.pattern: item for item in occurrences}

    assert set(by_pattern) == {d0, a0, d1}
    assert by_pattern[d0].center < by_pattern[a0].center < by_pattern[d1].center
    assert window.frame_ticks[0] < window.frame_ticks[1] < window.frame_ticks[2]


def test_life_gate_015_one_episode_is_not_enough_for_cross_agent_candidate():
    _world, _engine, decisions, _memory = _learn(gust_ids=(902,))

    a0 = sensor_pattern_id(SIGNAL_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    decision = _decision(decisions, a0, d1)

    assert decision.admitted is False
    assert "insufficient-repetitions" in decision.rejection_reasons
    assert "insufficient-independent-slices" in decision.rejection_reasons


def test_life_gate_015_repetition_discovers_specific_cross_agent_pairs_without_crossed_pairs():
    _world, engine, decisions, _memory = _learn(
        gust_ids=(911, 912, 913, 914),
        lull_ids=(915, 916, 917, 918),
    )

    a0 = sensor_pattern_id(SIGNAL_SENSOR, "a0")
    a1 = sensor_pattern_id(SIGNAL_SENSOR, "a1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    assert _key(a0, d1) in engine.links
    assert _key(a1, d2) in engine.links
    assert _key(a0, d2) not in engine.links
    assert _key(a1, d1) not in engine.links

    gust_link = engine.links[_key(a0, d1)]
    lull_link = engine.links[_key(a1, d2)]
    assert gust_link.repetitions == 4
    assert lull_link.repetitions == 4
    assert _decision(decisions, a0, d1).admitted is True
    assert _decision(decisions, a1, d2).admitted is True


def test_life_gate_015_memoria_recalls_agent_signal_to_matching_water_continuation():
    _world, _engine, _decisions, memory = _learn(
        gust_ids=(921, 922, 923, 924),
        lull_ids=(925, 926, 927, 928),
    )

    a0 = sensor_pattern_id(SIGNAL_SENSOR, "a0")
    a1 = sensor_pattern_id(SIGNAL_SENSOR, "a1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")

    gust_recall = recall_structural_temporal_neighbors(
        memory,
        _address(a0),
        min_independent_slices=3,
    )
    lull_recall = recall_structural_temporal_neighbors(
        memory,
        _address(a1),
        min_independent_slices=3,
    )

    gust_after = {
        item.pattern_address
        for item in gust_recall.neighbors
        if item.relation_to_query == "after_query"
    }
    lull_after = {
        item.pattern_address
        for item in lull_recall.neighbors
        if item.relation_to_query == "after_query"
    }

    assert _address(d1) in gust_after
    assert _address(d2) not in gust_after
    assert _address(d2) in lull_after
    assert _address(d1) not in lull_after


def test_life_gate_015_cross_agent_candidate_preserves_independent_episode_provenance():
    _world, _engine, decisions, _memory = _learn(
        gust_ids=(931, 932, 933, 934),
    )

    a0 = sensor_pattern_id(SIGNAL_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    candidate = _decision(decisions, a0, d1).candidate

    assert candidate is not None
    assert candidate.repetitions == 4
    assert len(candidate.supporting_slice_ids) == 4
    assert len(set(candidate.supporting_slice_ids)) == 4
    assert len(candidate.supporting_frame_ids) == 12
    assert len(set(candidate.supporting_frame_ids)) == 12


def test_life_gate_015_memoria_contains_no_hardcoded_cross_agent_semantics():
    _world, _engine, decisions, memory = _learn(
        gust_ids=(941, 942, 943, 944),
        lull_ids=(945, 946, 947, 948),
    )

    payloads = [
        candidate.to_payload()
        for candidate in admitted_candidates(decisions)
    ]
    serialized = (repr(payloads) + repr(memory.snapshot())).lower()

    for forbidden in (
        "wind",
        "gust",
        "lull",
        "water",
        "flow",
        "open_channel",
        "close_channel",
        "causes",
        "cause",
    ):
        assert forbidden not in serialized


def test_life_gate_015_direction_changes_when_sensor_timing_is_reversed():
    _world, _engine, _decisions, memory = _learn(
        gust_ids=(951, 952, 953, 954),
        signal_after_consequence=True,
    )

    a0 = sensor_pattern_id(SIGNAL_SENSOR, "a0")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")

    recall = recall_structural_temporal_neighbors(
        memory,
        _address(a0),
        min_independent_slices=3,
    )
    relation = next(
        item
        for item in recall.neighbors
        if item.pattern_address == _address(d1)
    )

    assert relation.relation_to_query == "before_query"


def test_life_gate_015_is_deterministic():
    a = _learn(
        gust_ids=(961, 962, 963, 964),
        lull_ids=(965, 966, 967, 968),
    )
    b = _learn(
        gust_ids=(961, 962, 963, 964),
        lull_ids=(965, 966, 967, 968),
    )

    _world_a, engine_a, decisions_a, memory_a = a
    _world_b, engine_b, decisions_b, memory_b = b

    assert decisions_a == decisions_b
    assert memory_a.snapshot() == memory_b.snapshot()
    assert tuple(
        sorted((key, link.rho, link.repetitions, link.mean_dt) for key, link in engine_a.links.items())
    ) == tuple(
        sorted((key, link.rho, link.repetitions, link.mean_dt) for key, link in engine_b.links.items())
    )
