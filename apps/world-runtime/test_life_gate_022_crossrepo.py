from __future__ import annotations

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
from scenario_life_gate_022 import build_life_gate_022_world


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
    world = build_life_gate_022_world(
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


def _with_proxy(
    rs: RealitySlice,
    *,
    episode_id: int,
    present: bool,
) -> RealitySlice:
    if not present:
        return rs
    occurrences = list(rs.occurrences)
    occurrences.append(
        Occurrence(
            pattern=sensor_pattern_id(PROXY_SENSOR, PROXY_BAND),
            modality=Modality.SENSOR,
            t_start=0.158,
            t_end=0.162,
            source=930001,
            provenance=730000 + episode_id,
        )
    )
    return RealitySlice(
        slice_id=rs.slice_id,
        t_start=rs.t_start,
        t_end=rs.t_end,
        occurrences=tuple(occurrences),
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


def _run_regime_shift():
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    observations = StructuralContextObservationMemory()
    admission = StructuralContextAdmissionStateMemory()
    phase_1_slice_ids = []
    phase_2_slice_ids = []
    episode_id = 1700

    def ingest_phase(*, proxy_context_phase: str, phase_slice_ids: list[int]):
        nonlocal episode_id, higher, policy
        last_world = None
        for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
            for _ in range(5):
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
                rs = _with_proxy(
                    window.reality_slice,
                    episode_id=episode_id,
                    present=(barrier_phase == proxy_context_phase),
                )
                pairwise.ingest(rs)
                higher.ingest(
                    rs,
                    pattern_support=pairwise.pattern_slices,
                )
                provenance[rs.slice_id] = window.frame_ids
                phase_slice_ids.append(rs.slice_id)
        return last_world

    phase_1_world = ingest_phase(
        proxy_context_phase="b_clear",
        phase_slice_ids=phase_1_slice_ids,
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
        supporting_slice_ids=tuple(phase_1_slice_ids),
    )

    phase_2_world = ingest_phase(
        proxy_context_phase="b_blocked",
        phase_slice_ids=phase_2_slice_ids,
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
        supporting_slice_ids=tuple(phase_2_slice_ids),
    )

    return {
        "phase_1_world": phase_1_world,
        "phase_2_world": phase_2_world,
        "pairwise": pairwise,
        "higher": higher,
        "policy": policy,
        "phase_1_candidates": phase_1_candidates,
        "phase_2_candidates": phase_2_candidates,
        "observations": observations,
        "admission": admission,
        "phase_1_slice_ids": tuple(phase_1_slice_ids),
        "phase_2_slice_ids": tuple(phase_2_slice_ids),
    }


def _false_phase_1_keys():
    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    a1 = sensor_pattern_id(AGENT_SENSOR, "a1")
    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")
    return {
        (tuple(sorted((a0, x0))), d1),
        (tuple(sorted((a1, x0))), d2),
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


def test_life_gate_022_phase_1_proxy_contexts_are_genuinely_admitted():
    state = _run_regime_shift()

    phase_1 = _candidate_map(state["phase_1_candidates"])
    for key in _false_phase_1_keys():
        assert key in phase_1
        candidate = phase_1[key]
        assert candidate.repetitions == 4
        assert candidate.context_reliability > 0.99
        assert all(
            0.49 < value < 0.51
            for value in candidate.lower_order_reliabilities
        )


def test_life_gate_022_same_proxy_contexts_lose_admission_after_regime_change():
    state = _run_regime_shift()

    phase_1 = _candidate_map(state["phase_1_candidates"])
    phase_2 = _candidate_map(state["phase_2_candidates"])
    assert _false_phase_1_keys().issubset(phase_1)
    assert _false_phase_1_keys().isdisjoint(phase_2)

    for antecedents, consequence in _false_phase_1_keys():
        link = state["higher"].links[
            (antecedents[0], antecedents[1], consequence)
        ]
        assert link.rho >= state["policy"].min_rho
        assert state["higher"].context_reliability(link) < 0.60
        assert (
            state["higher"].context_reliability(link)
            < state["policy"].min_context_reliability
        )


def test_life_gate_022_true_xor_contexts_remain_admitted_across_regimes():
    state = _run_regime_shift()
    phase_2 = _candidate_map(state["phase_2_candidates"])

    assert _true_keys().issubset(phase_2)
    for key in _true_keys():
        assert phase_2[key].context_reliability > 0.99


def test_life_gate_022_historical_recall_preserves_old_proxy_evidence_but_active_recall_drops_it():
    state = _run_regime_shift()

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    x0 = _address(sensor_pattern_id(PROXY_SENSOR, PROXY_BAND))
    d1 = _address(sensor_pattern_id(FLOW_SENSOR, "d1"))

    historical = recall_structural_context(
        state["observations"],
        (a0, x0),
        min_independent_slices=3,
    )
    active = recall_active_structural_context(
        state["observations"],
        state["admission"],
        (a0, x0),
        min_independent_slices=3,
    )

    assert tuple(x.consequence_pattern for x in historical.neighbors) == (d1,)
    assert active.neighbors == ()

    current = state["admission"].current((a0, x0))
    assert current is not None
    assert current.source_epoch_id == "phase-2"
    assert current.active_candidate_ids == ()


def test_life_gate_022_true_context_remains_active_after_regime_change():
    state = _run_regime_shift()

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    c0 = _address(sensor_pattern_id(CONTEXT_SENSOR, "c0"))
    d1 = _address(sensor_pattern_id(FLOW_SENSOR, "d1"))

    active = recall_active_structural_context(
        state["observations"],
        state["admission"],
        (a0, c0),
        min_independent_slices=3,
    )

    assert tuple(x.consequence_pattern for x in active.neighbors) == (d1,)


def test_life_gate_022_admission_audit_keeps_both_regime_snapshots():
    state = _run_regime_shift()

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    x0 = _address(sensor_pattern_id(PROXY_SENSOR, PROXY_BAND))
    context = tuple(sorted((a0, x0)))
    history = tuple(
        item
        for item in state["admission"].snapshot()
        if item.antecedent_patterns == context
    )

    assert len(history) == 2
    assert history[0].source_epoch_id == "phase-1"
    assert len(history[0].active_candidate_ids) == 1
    assert history[1].source_epoch_id == "phase-2"
    assert history[1].active_candidate_ids == ()


def test_life_gate_022_regime_shift_does_not_delete_structural_history():
    state = _run_regime_shift()

    false_candidate_ids = {
        candidate.candidate_id
        for key, candidate in _candidate_map(
            state["phase_1_candidates"]
        ).items()
        if key in _false_phase_1_keys()
    }
    remembered_ids = {
        item.source_candidate_id
        for item in state["observations"].snapshot()
    }

    assert false_candidate_ids.issubset(remembered_ids)


def test_life_gate_022_is_deterministic():
    a = _run_regime_shift()
    b = _run_regime_shift()

    assert a["phase_1_candidates"] == b["phase_1_candidates"]
    assert a["phase_2_candidates"] == b["phase_2_candidates"]
    assert a["observations"].snapshot() == b["observations"].snapshot()
    assert a["admission"].snapshot() == b["admission"].snapshot()
