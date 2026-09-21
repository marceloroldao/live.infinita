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
from scenario_life_gate_023 import build_life_gate_023_world


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
    world = build_life_gate_023_world(
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
    occurrences = list(rs.occurrences)
    base = rs.t_start
    occurrences.append(
        Occurrence(
            pattern=sensor_pattern_id(PROXY_SENSOR, PROXY_BAND),
            modality=Modality.SENSOR,
            t_start=base + 0.158,
            t_end=base + 0.162,
            source=940001,
            provenance=740000 + episode_id,
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


def _run_passive_forgetting():
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    observations = StructuralContextObservationMemory()
    admission = StructuralContextAdmissionStateMemory()
    episode_id = 1800
    sequence = 0

    def ingest_phase(*, proxy_present: bool):
        nonlocal episode_id, sequence, higher, policy
        phase_slices = []
        last_world = None

        # Round-robin ordering keeps true contexts regularly refreshed while time
        # advances monotonically across independent episodes.
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
                phase_slices.append(rs.slice_id)
        return last_world, tuple(phase_slices)

    phase_1_world, phase_1_slices = ingest_phase(proxy_present=True)
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

    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)
    proxy_support_after_phase_1 = pairwise.pattern_slices.get(x0, 0)
    proxy_link_state_after_phase_1 = {
        key: (
            higher.links[(key[0][0], key[0][1], key[1])].rho,
            higher.links[(key[0][0], key[0][1], key[1])].repetitions,
            higher.links[(key[0][0], key[0][1], key[1])].last_time,
            higher.context_slices[key[0]],
        )
        for key in _proxy_keys()
    }

    phase_2_world, phase_2_slices = ingest_phase(proxy_present=False)
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
        "proxy_support_after_phase_1": proxy_support_after_phase_1,
        "proxy_link_state_after_phase_1": proxy_link_state_after_phase_1,
    }


def test_life_gate_023_proxy_contexts_are_admitted_before_disappearance():
    state = _run_passive_forgetting()
    phase_1 = _candidate_map(state["phase_1_candidates"])

    assert _proxy_keys().issubset(phase_1)
    for key in _proxy_keys():
        candidate = phase_1[key]
        assert candidate.context_reliability > 0.99
        assert candidate.rho >= state["policy"].min_rho


def test_life_gate_023_proxy_disappears_entirely_in_phase_2():
    state = _run_passive_forgetting()
    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)

    assert state["proxy_support_after_phase_1"] == 10
    assert state["pairwise"].pattern_slices[x0] == 10

    for key, before in state["proxy_link_state_after_phase_1"].items():
        link = state["higher"].links[(key[0][0], key[0][1], key[1])]
        assert link.repetitions == before[1]
        assert link.last_time == before[2]
        assert state["higher"].context_slices[key[0]] == before[3]
        assert link.last_decay_time > link.last_time


def test_life_gate_023_passive_time_decay_removes_old_proxy_admission():
    state = _run_passive_forgetting()
    phase_1 = _candidate_map(state["phase_1_candidates"])
    phase_2 = _candidate_map(state["phase_2_candidates"])

    assert _proxy_keys().issubset(phase_1)
    assert _proxy_keys().isdisjoint(phase_2)

    for antecedents, consequence in _proxy_keys():
        link = state["higher"].links[
            (antecedents[0], antecedents[1], consequence)
        ]
        assert state["higher"].context_reliability(link) > 0.99
        assert link.rho < state["policy"].min_rho


def test_life_gate_023_true_contexts_stay_active_while_proxy_fades():
    state = _run_passive_forgetting()
    phase_2 = _candidate_map(state["phase_2_candidates"])

    assert _true_keys().issubset(phase_2)
    for key in _true_keys():
        candidate = phase_2[key]
        assert candidate.rho >= state["policy"].min_rho
        assert candidate.context_reliability > 0.99


def test_life_gate_023_historical_recall_keeps_proxy_but_active_recall_drops_it():
    state = _run_passive_forgetting()

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


def test_life_gate_023_true_context_recall_remains_active():
    state = _run_passive_forgetting()

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


def test_life_gate_023_decay_preserves_proxy_history_and_provenance():
    state = _run_passive_forgetting()

    phase_1_proxy_ids = {
        candidate.candidate_id
        for key, candidate in _candidate_map(
            state["phase_1_candidates"]
        ).items()
        if key in _proxy_keys()
    }
    remembered_ids = {
        item.source_candidate_id
        for item in state["observations"].snapshot()
    }

    assert phase_1_proxy_ids.issubset(remembered_ids)


def test_life_gate_023_is_deterministic():
    a = _run_passive_forgetting()
    b = _run_passive_forgetting()

    assert a["phase_1_candidates"] == b["phase_1_candidates"]
    assert a["phase_2_candidates"] == b["phase_2_candidates"]
    assert a["observations"].snapshot() == b["observations"].snapshot()
    assert a["admission"].snapshot() == b["admission"].snapshot()
