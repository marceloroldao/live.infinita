from __future__ import annotations

from dataclasses import replace

from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionStateMemory,
)
from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_context_recall_v2 import (
    recall_active_structural_context,
    recall_structural_context,
)
from reality_slice import Modality, Occurrence, RealitySlice, TemporalAssociator

from context_observation_memoria_adapter import (
    ingest_higher_order_context_candidate,
    refresh_higher_order_context_admission_state,
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
from scenario_life_gate_025 import build_life_gate_025_world


FLOW_SENSOR = "s_flow"
AGENT_SENSOR = "s_agent_signal_01"
CONTEXT_SENSOR = "s_context_signal_01"
PROXY_SENSOR = "s_regime_proxy_01"
PROXY_BAND = "x0"

COMBINATIONS = (
    ("w_gust_a", "b_clear", "a0", "c0", "d1"),
    ("w_gust_a", "b_blocked", "a0", "c1", "d2"),
    ("w_lull_a", "b_clear", "a1", "c0", "d2"),
    ("w_lull_a", "b_blocked", "a1", "c1", "d1"),
)


def _address(pattern_id: int) -> str:
    return f"temporal:pattern:{pattern_id}"


def _episode(episode_id: int, wind_phase_id: str, barrier_phase_id: str):
    world = build_life_gate_025_world(
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
    return world, reality_window_from_world_rule(world, observer_id="nova")


def _shift_slice(rs: RealitySlice, target_start: float) -> RealitySlice:
    delta = float(target_start) - rs.t_start
    return RealitySlice(
        slice_id=rs.slice_id,
        t_start=rs.t_start + delta,
        t_end=rs.t_end + delta,
        occurrences=tuple(
            Occurrence(
                pattern=item.pattern,
                modality=item.modality,
                t_start=item.t_start + delta,
                t_end=item.t_end + delta,
                source=item.source,
                provenance=item.provenance,
            )
            for item in rs.occurrences
        ),
        provenance=rs.provenance,
    )


def _with_proxy(
    rs: RealitySlice,
    *,
    episode_id: int,
    present: bool,
) -> RealitySlice:
    if not present:
        return rs
    base = rs.t_start
    return RealitySlice(
        slice_id=rs.slice_id,
        t_start=rs.t_start,
        t_end=rs.t_end,
        occurrences=tuple(rs.occurrences)
        + (
            Occurrence(
                pattern=sensor_pattern_id(PROXY_SENSOR, PROXY_BAND),
                modality=Modality.SENSOR,
                t_start=base + 0.158,
                t_end=base + 0.162,
                source=960001,
                provenance=760000 + episode_id,
            ),
        ),
        provenance=rs.provenance,
    )


def _candidate_map(candidates):
    return {
        (
            candidate.antecedent_patterns,
            candidate.consequence_pattern,
        ): candidate
        for candidate in candidates
    }


def _old_proxy_keys():
    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    a1 = sensor_pattern_id(AGENT_SENSOR, "a1")
    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")
    return {
        (tuple(sorted((a0, x0))), d1),
        (tuple(sorted((a1, x0))), d2),
    }


def _new_proxy_keys():
    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    a1 = sensor_pattern_id(AGENT_SENSOR, "a1")
    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")
    return {
        (tuple(sorted((a0, x0))), d2),
        (tuple(sorted((a1, x0))), d1),
    }


def _true_keys():
    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    a1 = sensor_pattern_id(AGENT_SENSOR, "a1")
    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    c1 = sensor_pattern_id(CONTEXT_SENSOR, "c1")
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")
    return {
        (tuple(sorted((a0, c0))), d1),
        (tuple(sorted((a0, c1))), d2),
        (tuple(sorted((a1, c0))), d2),
        (tuple(sorted((a1, c1))), d1),
    }


def _run_remapping():
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    observations = StructuralContextObservationMemory()
    admission = StructuralContextAdmissionStateMemory()
    episode_id = 3100
    sequence = 0

    def ingest_phase(*, proxy_context_phase: str | None):
        nonlocal episode_id, sequence, higher, policy
        slices = []
        last_world = None
        for _round in range(5):
            for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
                episode_id += 1
                sequence += 1
                world, window = _episode(
                    episode_id,
                    wind_phase,
                    barrier_phase,
                )
                last_world = world
                if policy is None:
                    policy = policy_from_world(world)
                    higher = make_sparse_context_associator(policy)

                rs = _shift_slice(
                    window.reality_slice,
                    target_start=float(sequence),
                )
                rs = _with_proxy(
                    rs,
                    episode_id=episode_id,
                    present=(
                        proxy_context_phase is not None
                        and barrier_phase == proxy_context_phase
                    ),
                )
                pairwise.ingest(rs)
                higher.ingest(
                    rs,
                    pattern_support=pairwise.pattern_slices,
                )
                provenance[rs.slice_id] = window.frame_ids
                slices.append(rs.slice_id)
        return last_world, tuple(slices)

    phase_1_world, phase_1_slices = ingest_phase(
        proxy_context_phase="b_clear",
    )
    phase_1_candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        policy,
        provenance_by_slice=provenance,
    )
    for candidate in phase_1_candidates:
        ingest_higher_order_context_candidate(observations, candidate)
    refresh_higher_order_context_admission_state(
        admission,
        phase_1_candidates,
        source_epoch_id="phase-1",
        supporting_slice_ids=phase_1_slices,
    )

    phase_2_world, phase_2_slices = ingest_phase(
        proxy_context_phase=None,
    )
    phase_2_candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        policy,
        provenance_by_slice=provenance,
    )
    for candidate in phase_2_candidates:
        ingest_higher_order_context_candidate(observations, candidate)
    refresh_higher_order_context_admission_state(
        admission,
        phase_2_candidates,
        source_epoch_id="phase-2",
        supporting_slice_ids=phase_2_slices,
    )

    phase_3_world, phase_3_slices = ingest_phase(
        proxy_context_phase="b_blocked",
    )
    phase_3_candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        policy,
        provenance_by_slice=provenance,
    )
    for candidate in phase_3_candidates:
        ingest_higher_order_context_candidate(observations, candidate)
    refresh_higher_order_context_admission_state(
        admission,
        phase_3_candidates,
        source_epoch_id="phase-3",
        supporting_slice_ids=phase_3_slices,
    )

    global_policy = replace(
        policy,
        active_evidence_slice_window=0,
    )
    global_phase_3_candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        global_policy,
        provenance_by_slice=provenance,
    )

    return {
        "phase_1_world": phase_1_world,
        "phase_2_world": phase_2_world,
        "phase_3_world": phase_3_world,
        "pairwise": pairwise,
        "higher": higher,
        "policy": policy,
        "phase_1_slices": phase_1_slices,
        "phase_2_slices": phase_2_slices,
        "phase_3_slices": phase_3_slices,
        "phase_1_candidates": phase_1_candidates,
        "phase_2_candidates": phase_2_candidates,
        "phase_3_candidates": phase_3_candidates,
        "global_phase_3_candidates": global_phase_3_candidates,
        "observations": observations,
        "admission": admission,
    }


def test_life_gate_025_old_mapping_is_admitted_then_forgotten():
    state = _run_remapping()
    phase_1 = _candidate_map(state["phase_1_candidates"])
    phase_2 = _candidate_map(state["phase_2_candidates"])

    assert _old_proxy_keys().issubset(phase_1)
    assert _old_proxy_keys().isdisjoint(phase_2)


def test_life_gate_025_accumulated_global_coverage_alone_cannot_admit_remap():
    state = _run_remapping()
    global_phase_3 = _candidate_map(state["global_phase_3_candidates"])

    assert _new_proxy_keys().isdisjoint(global_phase_3)


def test_life_gate_025_recent_structural_window_admits_only_new_mapping():
    state = _run_remapping()
    phase_3 = _candidate_map(state["phase_3_candidates"])

    assert _new_proxy_keys().issubset(phase_3)
    assert _old_proxy_keys().isdisjoint(phase_3)

    for key in _new_proxy_keys():
        candidate = phase_3[key]
        assert candidate.repetitions == 5
        assert candidate.context_coverage > 0.99
        assert candidate.context_reliability > 0.99
        assert set(candidate.supporting_slice_ids).issubset(
            set(state["phase_3_slices"])
        )
        assert len(candidate.supporting_slice_ids) == 5


def test_life_gate_025_historical_memory_keeps_old_and_new_consequences():
    state = _run_remapping()

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    x0 = _address(sensor_pattern_id(PROXY_SENSOR, PROXY_BAND))
    d1 = _address(sensor_pattern_id(FLOW_SENSOR, "d1"))
    d2 = _address(sensor_pattern_id(FLOW_SENSOR, "d2"))

    historical = recall_structural_context(
        state["observations"],
        (a0, x0),
        min_independent_slices=3,
    )

    assert tuple(
        item.consequence_pattern
        for item in historical.neighbors
    ) == tuple(sorted((d1, d2)))


def test_life_gate_025_active_recall_exposes_only_current_remapped_consequence():
    state = _run_remapping()

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    x0 = _address(sensor_pattern_id(PROXY_SENSOR, PROXY_BAND))
    d2 = _address(sensor_pattern_id(FLOW_SENSOR, "d2"))

    active = recall_active_structural_context(
        state["observations"],
        state["admission"],
        (a0, x0),
        min_independent_slices=3,
    )

    assert tuple(
        item.consequence_pattern
        for item in active.neighbors
    ) == (d2,)


def test_life_gate_025_old_and_new_candidate_ids_coexist_without_score_winner():
    state = _run_remapping()
    phase_1 = _candidate_map(state["phase_1_candidates"])
    phase_3 = _candidate_map(state["phase_3_candidates"])

    for old_key in _old_proxy_keys():
        antecedents, old_consequence = old_key
        new_key = next(
            key
            for key in _new_proxy_keys()
            if key[0] == antecedents
        )
        assert old_consequence != new_key[1]
        assert phase_1[old_key].candidate_id != phase_3[new_key].candidate_id

    remembered = {
        item.source_candidate_id
        for item in state["observations"].snapshot()
    }
    for key in _old_proxy_keys():
        assert phase_1[key].candidate_id in remembered
    for key in _new_proxy_keys():
        assert phase_3[key].candidate_id in remembered


def test_life_gate_025_admission_history_is_old_active_inactive_new_active():
    state = _run_remapping()

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    x0 = _address(sensor_pattern_id(PROXY_SENSOR, PROXY_BAND))
    context = tuple(sorted((a0, x0)))
    history = tuple(
        item
        for item in state["admission"].snapshot()
        if item.antecedent_patterns == context
    )

    assert tuple(item.source_epoch_id for item in history) == (
        "phase-1",
        "phase-2",
        "phase-3",
    )
    assert len(history[0].active_candidate_ids) == 1
    assert history[1].active_candidate_ids == ()
    assert len(history[2].active_candidate_ids) == 1
    assert history[2].active_candidate_ids != history[0].active_candidate_ids


def test_life_gate_025_true_xor_contexts_remain_active():
    state = _run_remapping()
    phase_3 = _candidate_map(state["phase_3_candidates"])

    assert _true_keys().issubset(phase_3)
    for key in _true_keys():
        assert phase_3[key].context_reliability > 0.99


def test_life_gate_025_recent_window_preserves_global_historical_links():
    state = _run_remapping()

    for key in _old_proxy_keys() | _new_proxy_keys():
        antecedents, consequence = key
        assert (
            antecedents[0],
            antecedents[1],
            consequence,
        ) in state["higher"].links

    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)
    context = tuple(sorted((a0, x0)))
    # The first phase-1 proxy occurrence establishes min_pattern_support and is
    # intentionally not allocated into the higher-order context index.
    assert len(state["higher"].context_seen_slices[context]) == 9


def test_life_gate_025_is_deterministic():
    a = _run_remapping()
    b = _run_remapping()

    assert a["phase_1_candidates"] == b["phase_1_candidates"]
    assert a["phase_2_candidates"] == b["phase_2_candidates"]
    assert a["phase_3_candidates"] == b["phase_3_candidates"]
    assert a["global_phase_3_candidates"] == b["global_phase_3_candidates"]
    assert a["observations"].snapshot() == b["observations"].snapshot()
    assert a["admission"].snapshot() == b["admission"].snapshot()
