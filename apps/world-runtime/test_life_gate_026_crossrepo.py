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
    refresh_higher_order_context_resolution_state,
)
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from environmental_state_interaction_runtime import apply_environmental_state_interactions
from higher_order_context_selector import (
    make_sparse_context_associator,
    policy_from_world,
    resolve_higher_order_context_states,
    select_higher_order_context_candidates,
)
from reality_slice_bridge import reality_window_from_world_rule, sensor_pattern_id
from scenario_life_gate_026 import build_life_gate_026_world


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
    world = build_life_gate_026_world(
        episode_id=episode_id,
        wind_phase_id=wind_phase_id,
        barrier_phase_id=barrier_phase_id,
    )
    world = sample_multimodal_sensor_frame(
        world, observer_id="nova", sensor_ids=(FLOW_SENSOR,)
    ).world
    world = sample_multimodal_sensor_frame(
        world, observer_id="nova", sensor_ids=(AGENT_SENSOR,)
    ).world
    world = sample_multimodal_sensor_frame(
        world, observer_id="nova", sensor_ids=(CONTEXT_SENSOR,)
    ).world

    interacted = apply_environmental_state_interactions(world)
    physical = advance_distributed_environmental_agents(
        interacted.world, ticks=1
    )[0]
    world = sample_multimodal_sensor_frame(
        physical.world, observer_id="nova", sensor_ids=(FLOW_SENSOR,)
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


def _with_proxy(rs: RealitySlice, *, episode_id: int, present: bool) -> RealitySlice:
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
                source=970001,
                provenance=770000 + episode_id,
            ),
        ),
        provenance=rs.provenance,
    )


def _proxy_contexts():
    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    a1 = sensor_pattern_id(AGENT_SENSOR, "a1")
    x0 = sensor_pattern_id(PROXY_SENSOR, PROXY_BAND)
    return (
        tuple(sorted((a0, x0))),
        tuple(sorted((a1, x0))),
    )


def _old_new_consequences():
    d1 = sensor_pattern_id(FLOW_SENSOR, "d1")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")
    contexts = _proxy_contexts()
    return {
        contexts[0]: (d1, d2),
        contexts[1]: (d2, d1),
    }


def _resolution_map(resolutions):
    return {
        resolution.antecedent_patterns: resolution
        for resolution in resolutions
    }


def _candidate_map(candidates):
    return {
        (candidate.antecedent_patterns, candidate.consequence_pattern): candidate
        for candidate in candidates
    }


def _run_gradual_remap():
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    observations = StructuralContextObservationMemory()
    admission = StructuralContextAdmissionStateMemory()
    episode_id = 4100
    sequence = 0

    def ingest_round(proxy_context_phase: str):
        nonlocal episode_id, sequence, higher, policy
        slice_ids = []
        for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
            episode_id += 1
            sequence += 1
            world, window = _episode(
                episode_id, wind_phase, barrier_phase
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
                present=(barrier_phase == proxy_context_phase),
            )
            pairwise.ingest(rs)
            higher.ingest(rs, pattern_support=pairwise.pattern_slices)
            provenance[rs.slice_id] = window.frame_ids
            slice_ids.append(rs.slice_id)
        return tuple(slice_ids)

    initial_slices = []
    for _ in range(5):
        initial_slices.extend(ingest_round("b_clear"))

    initial_candidates = select_higher_order_context_candidates(
        pairwise, higher, policy, provenance_by_slice=provenance
    )
    for candidate in initial_candidates:
        ingest_higher_order_context_candidate(observations, candidate)
    initial_resolutions = resolve_higher_order_context_states(
        pairwise, higher, policy
    )
    refresh_higher_order_context_resolution_state(
        admission,
        initial_resolutions,
        source_epoch_id="initial",
        supporting_slice_ids=tuple(initial_slices),
    )

    checkpoints = []
    for round_number in range(1, 5):
        round_slices = ingest_round("b_blocked")
        candidates = select_higher_order_context_candidates(
            pairwise, higher, policy, provenance_by_slice=provenance
        )
        for candidate in candidates:
            ingest_higher_order_context_candidate(observations, candidate)
        resolutions = resolve_higher_order_context_states(
            pairwise, higher, policy
        )
        refresh_higher_order_context_resolution_state(
            admission,
            resolutions,
            source_epoch_id=f"transition-{round_number}",
            supporting_slice_ids=round_slices,
        )
        checkpoints.append(
            {
                "round": round_number,
                "candidates": candidates,
                "resolutions": resolutions,
            }
        )

    return {
        "pairwise": pairwise,
        "higher": higher,
        "policy": policy,
        "observations": observations,
        "admission": admission,
        "initial_candidates": initial_candidates,
        "initial_resolutions": initial_resolutions,
        "checkpoints": tuple(checkpoints),
    }


def _hypothesis_for(resolution, consequence):
    return next(
        item
        for item in resolution.hypotheses
        if item.consequence_pattern == consequence
    )


def test_life_gate_026_transition_states_are_resolved_ambiguous_ambiguous_resolved():
    state = _run_gradual_remap()
    initial = _resolution_map(state["initial_resolutions"])
    checkpoints = [
        _resolution_map(item["resolutions"])
        for item in state["checkpoints"]
    ]

    for context in _proxy_contexts():
        assert initial[context].resolution_state == "resolved"
        assert checkpoints[0][context].resolution_state == "resolved"
        assert checkpoints[1][context].resolution_state == "ambiguous"
        assert checkpoints[2][context].resolution_state == "ambiguous"
        assert checkpoints[3][context].resolution_state == "resolved"


def test_life_gate_026_recent_coverages_cross_without_premature_winner():
    state = _run_gradual_remap()
    checkpoints = [
        _resolution_map(item["resolutions"])
        for item in state["checkpoints"]
    ]

    for context, (old_consequence, new_consequence) in _old_new_consequences().items():
        expected = (
            (0.8, 0.2),
            (0.6, 0.4),
            (0.4, 0.6),
            (0.2, 0.8),
        )
        for resolution_map, (old_expected, new_expected) in zip(
            checkpoints, expected
        ):
            resolution = resolution_map[context]
            old = _hypothesis_for(resolution, old_consequence)
            new = _hypothesis_for(resolution, new_consequence)
            assert abs(old.context_coverage - old_expected) < 1e-9
            assert abs(new.context_coverage - new_expected) < 1e-9


def test_life_gate_026_ambiguous_state_has_no_active_candidate_and_two_competitors():
    state = _run_gradual_remap()

    for transition in ("transition-2", "transition-3"):
        for context in _proxy_contexts():
            addresses = tuple(_address(value) for value in context)
            snapshot = next(
                item
                for item in state["admission"].snapshot()
                if item.antecedent_patterns == tuple(sorted(addresses))
                and item.source_epoch_id == transition
            )
            assert snapshot.resolution_state == "ambiguous"
            assert snapshot.active_candidate_ids == ()
            assert len(snapshot.competing_candidate_ids) == 2


def test_life_gate_026_active_recall_is_empty_during_ambiguity():
    state = _run_gradual_remap()
    admission = StructuralContextAdmissionStateMemory()

    # Replay admission snapshots only through transition-2, then query current recall.
    for item in state["admission"].snapshot():
        admission.ingest_snapshot(
            antecedent_patterns=item.antecedent_patterns,
            active_candidate_ids=item.active_candidate_ids,
            source_epoch_id=item.source_epoch_id,
            supporting_slice_ids=item.supporting_slice_ids,
            provenance=item.provenance,
            resolution_state=item.resolution_state,
            competing_candidate_ids=item.competing_candidate_ids,
        )
        if item.source_epoch_id == "transition-2":
            # All contexts for this epoch are contiguous; current exact context state
            # can now be checked as soon as its transition-2 snapshot is replayed.
            if item.antecedent_patterns == tuple(
                sorted(_address(x) for x in _proxy_contexts()[0])
            ):
                recall = recall_active_structural_context(
                    state["observations"],
                    admission,
                    item.antecedent_patterns,
                    min_independent_slices=3,
                )
                assert recall.neighbors == ()
                break


def test_life_gate_026_final_active_recall_switches_to_new_consequence():
    state = _run_gradual_remap()

    for context, (_old_consequence, new_consequence) in _old_new_consequences().items():
        addresses = tuple(_address(value) for value in context)
        active = recall_active_structural_context(
            state["observations"],
            state["admission"],
            addresses,
            min_independent_slices=3,
        )
        assert tuple(
            item.consequence_pattern for item in active.neighbors
        ) == (_address(new_consequence),)


def test_life_gate_026_historical_recall_preserves_both_consequences():
    state = _run_gradual_remap()

    for context, (old_consequence, new_consequence) in _old_new_consequences().items():
        historical = recall_structural_context(
            state["observations"],
            tuple(_address(value) for value in context),
            min_independent_slices=3,
        )
        assert tuple(
            item.consequence_pattern for item in historical.neighbors
        ) == tuple(
            sorted((_address(old_consequence), _address(new_consequence)))
        )


def test_life_gate_026_final_resolution_activates_new_candidate_only():
    state = _run_gradual_remap()
    final_resolutions = _resolution_map(
        state["checkpoints"][-1]["resolutions"]
    )
    final_candidates = _candidate_map(
        state["checkpoints"][-1]["candidates"]
    )

    for context, (old_consequence, new_consequence) in _old_new_consequences().items():
        resolution = final_resolutions[context]
        assert resolution.resolution_state == "resolved"
        assert len(resolution.active_candidate_ids) == 1
        assert resolution.competing_candidate_ids == ()
        assert (
            context,
            new_consequence,
        ) in final_candidates
        assert (
            context,
            old_consequence,
        ) not in final_candidates


def test_life_gate_026_is_deterministic():
    a = _run_gradual_remap()
    b = _run_gradual_remap()

    assert a["initial_candidates"] == b["initial_candidates"]
    assert a["initial_resolutions"] == b["initial_resolutions"]
    assert a["checkpoints"] == b["checkpoints"]
    assert a["observations"].snapshot() == b["observations"].snapshot()
    assert a["admission"].snapshot() == b["admission"].snapshot()
