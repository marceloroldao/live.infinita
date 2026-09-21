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
from scenario_life_gate_027 import build_life_gate_027_world


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


def _episode(episode_id: int, wind_phase_id: str, barrier_phase_id: str):
    world = build_life_gate_027_world(
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


def _noise_slice(
    *,
    slice_id: int,
    pattern_id: int,
    end_time: float,
    duration: float,
) -> RealitySlice:
    start = end_time - duration
    return RealitySlice(
        slice_id=slice_id,
        t_start=start,
        t_end=end_time,
        occurrences=(
            Occurrence(
                pattern=pattern_id,
                modality=Modality.SENSOR,
                t_start=start + duration * .2,
                t_end=start + duration * .8,
                source=980001,
                provenance=780000 + slice_id,
            ),
        ),
    )


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


def _candidate_keys(candidates):
    return {
        (candidate.antecedent_patterns, candidate.consequence_pattern)
        for candidate in candidates
    }


def _resolution_map(resolutions):
    return {
        resolution.antecedent_patterns: resolution
        for resolution in resolutions
    }


def _build_rate_case(noise_count: int):
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    relevant_slice_ids = []
    episode_id = 5100
    sequence = 0

    for _round in range(5):
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
            pairwise.ingest(rs)
            higher.ingest(rs, pattern_support=pairwise.pattern_slices)
            provenance[rs.slice_id] = window.frame_ids
            relevant_slice_ids.append(rs.slice_id)

    initial_candidates = select_higher_order_context_candidates(
        pairwise, higher, policy, provenance_by_slice=provenance
    )
    initial_resolutions = resolve_higher_order_context_states(
        pairwise, higher, policy
    )

    last_relevant_end = max(
        higher.slice_end_times[slice_id]
        for slice_id in relevant_slice_ids
    )
    stress = world["rules"]["higher_order_event_rate_stress"]
    physical_span = float(stress["noise_physical_span"])
    step = physical_span / noise_count
    duration = min(.001, step * .5)

    for offset in range(noise_count):
        end_time = last_relevant_end + (offset + 1) * step
        rs = _noise_slice(
            slice_id=900000 + noise_count * 1000 + offset,
            pattern_id=sensor_pattern_id(
                f"s_rate_noise_{noise_count}_{offset}",
                "n0",
            ),
            end_time=end_time,
            duration=duration,
        )
        pairwise.ingest(rs)
        higher.ingest(rs, pattern_support=pairwise.pattern_slices)

    count_policy = replace(
        policy,
        active_evidence_slice_window=int(stress["count_window"]),
        active_evidence_time_window=0.0,
    )
    time_policy = policy

    count_candidates = select_higher_order_context_candidates(
        pairwise, higher, count_policy, provenance_by_slice=provenance
    )
    time_candidates = select_higher_order_context_candidates(
        pairwise, higher, time_policy, provenance_by_slice=provenance
    )
    count_resolutions = resolve_higher_order_context_states(
        pairwise, higher, count_policy
    )
    time_resolutions = resolve_higher_order_context_states(
        pairwise, higher, time_policy
    )

    return {
        "pairwise": pairwise,
        "higher": higher,
        "policy": policy,
        "count_policy": count_policy,
        "relevant_slice_ids": tuple(relevant_slice_ids),
        "initial_candidates": initial_candidates,
        "initial_resolutions": initial_resolutions,
        "count_candidates": count_candidates,
        "time_candidates": time_candidates,
        "count_resolutions": count_resolutions,
        "time_resolutions": time_resolutions,
        "final_time": max(higher.slice_end_times.values()),
    }


def test_life_gate_027_count_window_changes_only_because_event_rate_changes():
    slow = _build_rate_case(2)
    fast = _build_rate_case(100)

    assert _candidate_keys(slow["count_candidates"]) == _true_keys()
    assert fast["count_candidates"] == ()

    assert len(slow["higher"].recent_slice_ids(20)) == 20
    assert len(fast["higher"].recent_slice_ids(20)) == 20
    assert set(fast["higher"].recent_slice_ids(20)).isdisjoint(
        set(fast["relevant_slice_ids"])
    )


def test_life_gate_027_time_window_is_invariant_to_irrelevant_event_rate():
    slow = _build_rate_case(2)
    fast = _build_rate_case(100)

    assert slow["final_time"] == fast["final_time"]
    assert _candidate_keys(slow["time_candidates"]) == _true_keys()
    assert _candidate_keys(fast["time_candidates"]) == _true_keys()
    assert slow["time_candidates"] == fast["time_candidates"]
    assert slow["time_resolutions"] == fast["time_resolutions"]


def test_life_gate_027_time_window_preserves_relevant_support_under_fast_noise():
    fast = _build_rate_case(100)
    active = set(
        fast["higher"].recent_slice_ids_by_time(
            fast["policy"].active_evidence_time_window,
            now=fast["final_time"],
        )
    )

    assert set(fast["relevant_slice_ids"]).issubset(active)
    assert len(active) == len(fast["relevant_slice_ids"]) + 100

    for candidate in fast["time_candidates"]:
        assert set(candidate.supporting_slice_ids).issubset(
            set(fast["relevant_slice_ids"])
        )
        assert candidate.context_reliability > .99


def test_life_gate_027_high_rate_one_shot_noise_does_not_allocate_higher_order_links():
    slow = _build_rate_case(2)
    fast = _build_rate_case(100)

    assert set(slow["higher"].links) == set(fast["higher"].links)
    assert len(slow["higher"].links) == len(fast["higher"].links)


def test_life_gate_027_count_window_can_false_deactivate_current_memoria_state():
    fast = _build_rate_case(100)

    observations = StructuralContextObservationMemory()
    for candidate in fast["initial_candidates"]:
        ingest_higher_order_context_candidate(observations, candidate)

    count_admission = StructuralContextAdmissionStateMemory()
    refresh_higher_order_context_resolution_state(
        count_admission,
        fast["initial_resolutions"],
        source_epoch_id="initial",
        supporting_slice_ids=fast["relevant_slice_ids"],
    )
    refresh_higher_order_context_resolution_state(
        count_admission,
        fast["count_resolutions"],
        source_epoch_id="after-fast-noise-count",
    )

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    c0 = _address(sensor_pattern_id(CONTEXT_SENSOR, "c0"))
    active = recall_active_structural_context(
        observations,
        count_admission,
        (a0, c0),
        min_independent_slices=3,
    )

    assert active.neighbors == ()
    current = count_admission.current((a0, c0))
    assert current is not None
    assert current.resolution_state == "unsupported"


def test_life_gate_027_time_window_keeps_memoria_state_active_at_same_physical_time():
    fast = _build_rate_case(100)

    observations = StructuralContextObservationMemory()
    for candidate in fast["initial_candidates"]:
        ingest_higher_order_context_candidate(observations, candidate)

    time_admission = StructuralContextAdmissionStateMemory()
    refresh_higher_order_context_resolution_state(
        time_admission,
        fast["initial_resolutions"],
        source_epoch_id="initial",
        supporting_slice_ids=fast["relevant_slice_ids"],
    )
    refresh_higher_order_context_resolution_state(
        time_admission,
        fast["time_resolutions"],
        source_epoch_id="after-fast-noise-time",
    )

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    c0 = _address(sensor_pattern_id(CONTEXT_SENSOR, "c0"))
    d1 = _address(sensor_pattern_id(FLOW_SENSOR, "d1"))
    active = recall_active_structural_context(
        observations,
        time_admission,
        (a0, c0),
        min_independent_slices=3,
    )

    assert tuple(
        item.consequence_pattern for item in active.neighbors
    ) == (d1,)
    current = time_admission.current((a0, c0))
    assert current is not None
    assert current.resolution_state == "resolved"


def test_life_gate_027_time_window_is_deterministic():
    a = _build_rate_case(100)
    b = _build_rate_case(100)

    assert a["time_candidates"] == b["time_candidates"]
    assert a["time_resolutions"] == b["time_resolutions"]
    assert a["final_time"] == b["final_time"]
