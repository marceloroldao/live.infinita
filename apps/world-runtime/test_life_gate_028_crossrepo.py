from __future__ import annotations

from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionStateMemory,
)
from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_context_recall_v2 import (
    recall_active_structural_context,
)
from reality_slice import (
    Modality,
    Occurrence,
    RealitySlice,
    RealitySliceReorderBuffer,
    TemporalAssociator,
)

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
from reality_slice_event_time_runtime import (
    flush_reality_slice_event_time,
    ingest_reality_slice_event_time,
)
from scenario_life_gate_028 import build_life_gate_028_world


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
    world = build_life_gate_028_world(
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


def _higher_signature(higher):
    return tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                link.mean_delay,
                link.variance_delay,
                tuple(sorted(link.seen_slices)),
                link.last_time,
                link.last_decay_time,
            )
            for key, link in higher.links.items()
        )
    )


def _pairwise_signature(pairwise):
    return tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                link.mean_dt,
                link.variance_dt,
                tuple(sorted(link.seen_slices)),
                link.last_time,
            )
            for key, link in pairwise.links.items()
        )
    )


def _build_relevant_slices():
    slices = []
    provenance = {}
    world = None
    episode_id = 6100
    sequence = 0

    for _round in range(5):
        for wind_phase, barrier_phase, _a, _c, _d in COMBINATIONS:
            episode_id += 1
            sequence += 1
            world, window = _episode(
                episode_id, wind_phase, barrier_phase
            )
            rs = _shift_slice(
                window.reality_slice,
                target_start=float(sequence),
            )
            slices.append(rs)
            provenance[rs.slice_id] = window.frame_ids

    return world, tuple(slices), provenance


def _scrambled_arrival(slices):
    output = []
    order = (3, 1, 0, 2)
    for start in range(0, len(slices), 4):
        block = slices[start : start + 4]
        output.extend(block[index] for index in order)
    return tuple(output)


def _late_conflict_slice():
    a0 = sensor_pattern_id(AGENT_SENSOR, "a0")
    c0 = sensor_pattern_id(CONTEXT_SENSOR, "c0")
    d2 = sensor_pattern_id(FLOW_SENSOR, "d2")
    return RealitySlice(
        slice_id=999_028,
        t_start=9.0,
        t_end=10.0,
        occurrences=(
            Occurrence(
                pattern=a0,
                modality=Modality.SENSOR,
                t_start=9.10,
                t_end=9.12,
                source=990001,
                provenance=790001,
            ),
            Occurrence(
                pattern=c0,
                modality=Modality.SENSOR,
                t_start=9.20,
                t_end=9.22,
                source=990002,
                provenance=790002,
            ),
            Occurrence(
                pattern=d2,
                modality=Modality.SENSOR,
                t_start=9.55,
                t_end=9.57,
                source=990003,
                provenance=790003,
            ),
        ),
        provenance=(790001, 790002, 790003),
    )


def _run_arrival_case(*, scrambled: bool, inject_late: bool):
    world, chronological, provenance = _build_relevant_slices()
    policy = policy_from_world(world)
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = make_sparse_context_associator(policy)
    reorder = RealitySliceReorderBuffer(
        allowed_lateness=float(
            world["rules"]["reality_slice_event_time"]["allowed_lateness"]
        )
    )

    arrivals = _scrambled_arrival(chronological) if scrambled else chronological
    ingested_ids = []
    rejected = []

    for rs in arrivals:
        result = ingest_reality_slice_event_time(
            reorder,
            pairwise,
            higher,
            rs,
        )
        ingested_ids.extend(result.ingested_slice_ids)
        rejected.extend(result.batch.rejected)

    watermark_before_late = reorder.watermark
    max_event_time_before_late = reorder.max_event_time

    if inject_late:
        result = ingest_reality_slice_event_time(
            reorder,
            pairwise,
            higher,
            _late_conflict_slice(),
        )
        ingested_ids.extend(result.ingested_slice_ids)
        rejected.extend(result.batch.rejected)

    flushed = flush_reality_slice_event_time(
        reorder,
        pairwise,
        higher,
    )
    ingested_ids.extend(flushed.ingested_slice_ids)
    rejected.extend(flushed.batch.rejected)

    candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        policy,
        provenance_by_slice=provenance,
    )
    resolutions = resolve_higher_order_context_states(
        pairwise,
        higher,
        policy,
    )

    observations = StructuralContextObservationMemory()
    for candidate in candidates:
        ingest_higher_order_context_candidate(observations, candidate)
    admission = StructuralContextAdmissionStateMemory()
    refresh_higher_order_context_resolution_state(
        admission,
        resolutions,
        source_epoch_id="current",
        supporting_slice_ids=tuple(ingested_ids),
    )

    return {
        "world": world,
        "chronological": chronological,
        "policy": policy,
        "pairwise": pairwise,
        "higher": higher,
        "reorder": reorder,
        "ingested_ids": tuple(ingested_ids),
        "rejected": tuple(rejected),
        "watermark_before_late": watermark_before_late,
        "max_event_time_before_late": max_event_time_before_late,
        "candidates": candidates,
        "resolutions": resolutions,
        "observations": observations,
        "admission": admission,
    }


def test_life_gate_028_bounded_out_of_order_arrival_matches_in_order_learning():
    ordered = _run_arrival_case(scrambled=False, inject_late=False)
    scrambled = _run_arrival_case(scrambled=True, inject_late=False)

    chronological_ids = tuple(
        rs.slice_id for rs in ordered["chronological"]
    )

    assert ordered["ingested_ids"] == chronological_ids
    assert scrambled["ingested_ids"] == chronological_ids
    assert ordered["rejected"] == ()
    assert scrambled["rejected"] == ()
    assert _pairwise_signature(ordered["pairwise"]) == _pairwise_signature(
        scrambled["pairwise"]
    )
    assert _higher_signature(ordered["higher"]) == _higher_signature(
        scrambled["higher"]
    )
    assert ordered["candidates"] == scrambled["candidates"]
    assert ordered["resolutions"] == scrambled["resolutions"]
    assert _candidate_keys(scrambled["candidates"]) == _true_keys()


def test_life_gate_028_watermark_and_max_event_time_do_not_move_backward():
    state = _run_arrival_case(scrambled=True, inject_late=True)

    assert len(state["rejected"]) == 1
    rejection = state["rejected"][0]
    assert rejection.slice_id == 999_028
    assert rejection.event_time == 10.0
    assert rejection.watermark == state["watermark_before_late"]
    assert state["reorder"].watermark == state["watermark_before_late"]
    assert state["reorder"].max_event_time == state["max_event_time_before_late"]
    assert rejection.event_time < rejection.watermark


def test_life_gate_028_too_late_conflict_cannot_enter_structural_history():
    clean = _run_arrival_case(scrambled=True, inject_late=False)
    late = _run_arrival_case(scrambled=True, inject_late=True)

    assert late["ingested_ids"] == clean["ingested_ids"]
    assert _pairwise_signature(late["pairwise"]) == _pairwise_signature(
        clean["pairwise"]
    )
    assert _higher_signature(late["higher"]) == _higher_signature(
        clean["higher"]
    )
    assert late["candidates"] == clean["candidates"]
    assert late["resolutions"] == clean["resolutions"]

    for link in late["higher"].links.values():
        assert 999_028 not in link.seen_slices
    assert 999_028 not in late["higher"].slice_end_times


def test_life_gate_028_too_late_conflict_cannot_change_active_recall():
    clean = _run_arrival_case(scrambled=True, inject_late=False)
    late = _run_arrival_case(scrambled=True, inject_late=True)

    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    c0 = _address(sensor_pattern_id(CONTEXT_SENSOR, "c0"))
    d1 = _address(sensor_pattern_id(FLOW_SENSOR, "d1"))

    clean_active = recall_active_structural_context(
        clean["observations"],
        clean["admission"],
        (a0, c0),
        min_independent_slices=3,
    )
    late_active = recall_active_structural_context(
        late["observations"],
        late["admission"],
        (a0, c0),
        min_independent_slices=3,
    )

    assert tuple(
        item.consequence_pattern for item in clean_active.neighbors
    ) == (d1,)
    assert late_active == clean_active


def test_life_gate_028_delayed_but_valid_slices_are_not_discarded():
    state = _run_arrival_case(scrambled=True, inject_late=False)
    expected = {
        rs.slice_id
        for rs in state["chronological"]
    }

    assert set(state["ingested_ids"]) == expected
    assert len(state["ingested_ids"]) == 20
    assert state["rejected"] == ()
    assert state["reorder"].pending_slice_ids() == ()


def test_life_gate_028_is_deterministic():
    a = _run_arrival_case(scrambled=True, inject_late=True)
    b = _run_arrival_case(scrambled=True, inject_late=True)

    assert a["ingested_ids"] == b["ingested_ids"]
    assert a["rejected"] == b["rejected"]
    assert _pairwise_signature(a["pairwise"]) == _pairwise_signature(
        b["pairwise"]
    )
    assert _higher_signature(a["higher"]) == _higher_signature(
        b["higher"]
    )
    assert a["candidates"] == b["candidates"]
    assert a["resolutions"] == b["resolutions"]
    assert a["observations"].snapshot() == b["observations"].snapshot()
    assert a["admission"].snapshot() == b["admission"].snapshot()
