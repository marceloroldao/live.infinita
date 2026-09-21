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
from scenario_life_gate_024 import build_life_gate_024_world


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
    world = build_life_gate_024_world(
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
                source=950001,
                provenance=750000 + episode_id,
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


def _proxy_keys():
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


def _link(higher, key):
    antecedents, consequence = key
    return higher.links[(antecedents[0], antecedents[1], consequence)]


def _run_reacquisition():
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    observations = StructuralContextObservationMemory()
    admission = StructuralContextAdmissionStateMemory()
    episode_id = 1900
    sequence = 0

    def ingest_round(*, proxy_present: bool):
        nonlocal episode_id, sequence, higher, policy
        slices = []
        last_world = None
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
                    proxy_present
                    and barrier_phase == "b_clear"
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

    phase_1_slices = []
    phase_1_world = None
    for _ in range(5):
        phase_1_world, round_slices = ingest_round(proxy_present=True)
        phase_1_slices.extend(round_slices)

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
        supporting_slice_ids=tuple(phase_1_slices),
    )
    phase_1_proxy = {
        key: (
            _link(higher, key).rho,
            _link(higher, key).repetitions,
            tuple(sorted(_link(higher, key).seen_slices)),
            _link(higher, key).last_time,
        )
        for key in _proxy_keys()
    }

    phase_2_slices = []
    phase_2_world = None
    for _ in range(5):
        phase_2_world, round_slices = ingest_round(proxy_present=False)
        phase_2_slices.extend(round_slices)

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
        supporting_slice_ids=tuple(phase_2_slices),
    )
    forgotten_proxy = {
        key: (
            _link(higher, key).rho,
            _link(higher, key).repetitions,
            tuple(sorted(_link(higher, key).seen_slices)),
            _link(higher, key).last_time,
            _link(higher, key).last_decay_time,
        )
        for key in _proxy_keys()
    }

    phase_3_slices = []
    phase_3_candidates_by_round = []
    reacquired_round = {}
    first_return_proxy = None
    phase_3_world = None

    for round_number in range(1, 6):
        phase_3_world, round_slices = ingest_round(proxy_present=True)
        phase_3_slices.extend(round_slices)
        candidates = select_higher_order_context_candidates(
            pairwise,
            higher,
            policy,
            provenance_by_slice=provenance,
        )
        phase_3_candidates_by_round.append(candidates)
        cmap = _candidate_map(candidates)
        for key in _proxy_keys():
            if key in cmap and key not in reacquired_round:
                reacquired_round[key] = round_number
        if round_number == 1:
            first_return_proxy = {
                key: (
                    _link(higher, key).rho,
                    _link(higher, key).repetitions,
                    tuple(sorted(_link(higher, key).seen_slices)),
                    _link(higher, key).last_time,
                )
                for key in _proxy_keys()
            }

    phase_3_candidates = phase_3_candidates_by_round[-1]
    for candidate in phase_3_candidates:
        ingest_higher_order_context_candidate(observations, candidate)
    refresh_higher_order_context_admission_state(
        admission,
        phase_3_candidates,
        source_epoch_id="phase-3",
        supporting_slice_ids=tuple(phase_3_slices),
    )

    return {
        "phase_1_world": phase_1_world,
        "phase_2_world": phase_2_world,
        "phase_3_world": phase_3_world,
        "pairwise": pairwise,
        "higher": higher,
        "policy": policy,
        "phase_1_candidates": phase_1_candidates,
        "phase_2_candidates": phase_2_candidates,
        "phase_3_candidates": phase_3_candidates,
        "phase_3_candidates_by_round": tuple(phase_3_candidates_by_round),
        "reacquired_round": reacquired_round,
        "observations": observations,
        "admission": admission,
        "phase_1_proxy": phase_1_proxy,
        "forgotten_proxy": forgotten_proxy,
        "first_return_proxy": first_return_proxy,
    }


def _fresh_baseline_rounds():
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    episode_id = 2900
    sequence = 0
    admitted_round = {}

    for round_number in range(1, 6):
        for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
            episode_id += 1
            sequence += 1
            world, window = _episode(
                episode_id,
                wind_phase,
                barrier_phase,
            )
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
                present=(barrier_phase == "b_clear"),
            )
            pairwise.ingest(rs)
            higher.ingest(
                rs,
                pattern_support=pairwise.pattern_slices,
            )
            provenance[rs.slice_id] = window.frame_ids

        cmap = _candidate_map(
            select_higher_order_context_candidates(
                pairwise,
                higher,
                policy,
                provenance_by_slice=provenance,
            )
        )
        for key in _proxy_keys():
            if key in cmap and key not in admitted_round:
                admitted_round[key] = round_number

    return admitted_round


def test_life_gate_024_context_is_inactive_before_any_return_observation():
    state = _run_reacquisition()

    assert _proxy_keys().isdisjoint(
        _candidate_map(state["phase_2_candidates"])
    )
    for key in _proxy_keys():
        forgotten = state["forgotten_proxy"][key]
        assert forgotten[0] < state["policy"].min_rho


def test_life_gate_024_first_return_updates_from_decayed_state_not_historical_peak():
    state = _run_reacquisition()

    for key in _proxy_keys():
        phase_1 = state["phase_1_proxy"][key]
        forgotten = state["forgotten_proxy"][key]
        returned = state["first_return_proxy"][key]

        assert forgotten[0] < phase_1[0]
        assert returned[0] > forgotten[0]
        assert returned[1] == forgotten[1] + 1
        assert len(returned[2]) == len(forgotten[2]) + 1
        assert returned[3] > forgotten[3]


def test_life_gate_024_reacquisition_requires_actual_new_proxy_observation():
    state = _run_reacquisition()

    assert set(state["reacquired_round"]) == _proxy_keys()
    assert all(
        round_number >= 1
        for round_number in state["reacquired_round"].values()
    )


def test_life_gate_024_reacquisition_is_not_slower_than_fresh_learning():
    state = _run_reacquisition()
    fresh = _fresh_baseline_rounds()

    assert set(fresh) == _proxy_keys()
    for key in _proxy_keys():
        assert state["reacquired_round"][key] <= fresh[key]


def test_life_gate_024_same_candidate_identity_reactivates_with_extended_provenance():
    state = _run_reacquisition()
    phase_1 = _candidate_map(state["phase_1_candidates"])
    phase_3 = _candidate_map(state["phase_3_candidates"])

    for key in _proxy_keys():
        old = phase_1[key]
        new = phase_3[key]
        assert new.candidate_id == old.candidate_id
        assert set(old.supporting_slice_ids).issubset(
            set(new.supporting_slice_ids)
        )
        assert len(new.supporting_slice_ids) > len(old.supporting_slice_ids)


def test_life_gate_024_admission_history_records_active_inactive_active_transition():
    state = _run_reacquisition()

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
    assert history[2].active_candidate_ids == history[0].active_candidate_ids


def test_life_gate_024_active_recall_returns_after_reacquisition_and_history_remains_auditable():
    state = _run_reacquisition()

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
    assert tuple(x.consequence_pattern for x in active.neighbors) == (d1,)

    proxy_observations = tuple(
        item
        for item in state["observations"].snapshot()
        if item.antecedent_patterns == tuple(sorted((a0, x0)))
        and item.consequence_pattern == d1
    )
    assert len(proxy_observations) >= 2
    assert len({item.source_candidate_id for item in proxy_observations}) == 1


def test_life_gate_024_true_contexts_remain_active_after_reacquisition():
    state = _run_reacquisition()
    phase_3 = _candidate_map(state["phase_3_candidates"])

    assert _true_keys().issubset(phase_3)
    for key in _true_keys():
        assert phase_3[key].context_reliability > 0.99


def test_life_gate_024_is_deterministic():
    a = _run_reacquisition()
    b = _run_reacquisition()

    assert a["phase_1_candidates"] == b["phase_1_candidates"]
    assert a["phase_2_candidates"] == b["phase_2_candidates"]
    assert a["phase_3_candidates"] == b["phase_3_candidates"]
    assert a["reacquired_round"] == b["reacquired_round"]
    assert a["observations"].snapshot() == b["observations"].snapshot()
    assert a["admission"].snapshot() == b["admission"].snapshot()
