from __future__ import annotations

from dataclasses import replace

from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from reality_slice import Modality, Occurrence, RealitySlice, TemporalAssociator

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
from scenario_life_gate_020 import build_life_gate_020_world


FLOW_SENSOR = "s_flow"
AGENT_SENSOR = "s_agent_signal_01"
CONTEXT_SENSOR = "s_context_signal_01"

COMBINATIONS = (
    ("w_gust_a", "b_clear", "a0", "c0", "d1"),
    ("w_gust_a", "b_blocked", "a0", "c1", "d2"),
    ("w_lull_a", "b_clear", "a1", "c0", "d2"),
    ("w_lull_a", "b_blocked", "a1", "c1", "d1"),
)


def _episode(
    episode_id: int,
    wind_phase_id: str,
    barrier_phase_id: str,
):
    world = build_life_gate_020_world(
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


def _augment_with_noise(
    rs: RealitySlice,
    *,
    episode_id: int,
    one_shot_count: int,
    recurring_count: int,
    reverse_input: bool = False,
) -> RealitySlice:
    occurrences = list(rs.occurrences)

    # One-shot patterns are deliberately placed inside/near the useful context window.
    # They are structurally dangerous noise unless recurrence prefiltering works.
    for index in range(one_shot_count):
        pattern = sensor_pattern_id(
            f"s_noise_once_{episode_id}_{index}",
            "n0",
        )
        start = 0.225 + (index % 24) * 0.008
        occurrences.append(
            Occurrence(
                pattern=pattern,
                modality=Modality.SENSOR,
                t_start=start,
                t_end=start + 0.004,
                source=900000 + index,
                provenance=700000 + episode_id,
            )
        )

    # Recurrent distractors are real recurring patterns, but live outside both the
    # context-span and consequence-delay windows of the useful interaction.
    for index in range(recurring_count):
        pattern = sensor_pattern_id(
            f"s_noise_recurrent_{index}",
            "r0",
        )
        start = 1.90 + index * 0.20
        occurrences.append(
            Occurrence(
                pattern=pattern,
                modality=Modality.SENSOR,
                t_start=start,
                t_end=start + 0.01,
                source=910000 + index,
                provenance=710000 + episode_id,
            )
        )

    if reverse_input:
        occurrences.reverse()

    return RealitySlice(
        slice_id=rs.slice_id,
        t_start=rs.t_start,
        t_end=max(item.t_end for item in occurrences) + 0.01,
        occurrences=tuple(occurrences),
        provenance=rs.provenance,
    )


def _signature(higher):
    return tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                link.mean_delay,
                link.variance_delay,
                tuple(sorted(link.seen_slices)),
            )
            for key, link in higher.links.items()
        )
    )


def _learn(*, noisy: bool, reverse_input: bool = False):
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    last_world = None
    episode_id = 1500

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

            rs = window.reality_slice
            if noisy:
                stress = world["rules"]["higher_order_stress"]
                rs = _augment_with_noise(
                    rs,
                    episode_id=episode_id,
                    one_shot_count=int(stress["one_shot_distractors"]),
                    recurring_count=int(stress["recurring_distractors"]),
                    reverse_input=reverse_input,
                )
            elif reverse_input:
                rs = replace(
                    rs,
                    occurrences=tuple(reversed(rs.occurrences)),
                )

            pairwise.ingest(rs)
            higher.ingest(
                rs,
                pattern_support=pairwise.pattern_slices,
            )
            provenance[rs.slice_id] = window.frame_ids

    candidates = select_higher_order_context_candidates(
        pairwise,
        higher,
        policy,
        provenance_by_slice=provenance,
    )
    memory = StructuralContextObservationMemory()
    for candidate in candidates:
        ingest_higher_order_context_candidate(memory, candidate)

    return last_world, pairwise, higher, candidates, memory


def test_life_gate_020_noise_expands_pattern_universe_without_expanding_higher_order_index():
    clean = _learn(noisy=False)
    noisy = _learn(noisy=True)

    _cw, clean_pairwise, clean_higher, clean_candidates, clean_memory = clean
    _nw, noisy_pairwise, noisy_higher, noisy_candidates, noisy_memory = noisy

    assert len(clean_pairwise.pattern_slices) == 7
    assert len(noisy_pairwise.pattern_slices) == 783

    assert len(clean_higher.links) == 8
    assert len(noisy_higher.links) == 8
    assert _signature(noisy_higher) == _signature(clean_higher)

    assert len(clean_candidates) == 4
    assert len(noisy_candidates) == 4
    assert noisy_candidates == clean_candidates

    assert len(clean_memory.snapshot()) == 4
    assert len(noisy_memory.snapshot()) == 4
    assert noisy_memory.snapshot() == clean_memory.snapshot()


def test_life_gate_020_one_shot_distractors_never_enter_higher_order_links():
    _world, _pairwise, higher, _candidates, _memory = _learn(noisy=True)

    one_shot_prefixes = {
        sensor_pattern_id(f"s_noise_once_{episode_id}_{index}", "n0")
        for episode_id in range(1501, 1517)
        for index in range(48)
    }
    indexed_patterns = {
        pattern
        for key in higher.links
        for pattern in key
    }

    assert indexed_patterns.isdisjoint(one_shot_prefixes)


def test_life_gate_020_recurring_late_distractors_are_not_admitted_as_contexts():
    _world, _pairwise, _higher, candidates, _memory = _learn(noisy=True)

    recurring = {
        sensor_pattern_id(f"s_noise_recurrent_{index}", "r0")
        for index in range(8)
    }
    admitted_patterns = {
        pattern
        for candidate in candidates
        for pattern in (
            *candidate.antecedent_patterns,
            candidate.consequence_pattern,
        )
    }

    assert admitted_patterns.isdisjoint(recurring)


def test_life_gate_020_admitted_to_observed_ratio_and_memory_growth_are_bounded():
    _world, pairwise, higher, candidates, memory = _learn(noisy=True)

    assert len(pairwise.pattern_slices) == 783
    assert len(higher.links) == 8
    assert len(candidates) == 4
    assert len(memory.snapshot()) == 4

    admitted_ratio = len(candidates) / len(higher.links)
    assert admitted_ratio == 0.5

    # The higher-order index is bounded by recurrent/temporally-local evidence, not
    # by the 783-pattern global universe.
    assert len(higher.links) < len(pairwise.pattern_slices) // 50


def test_life_gate_020_reordering_occurrence_input_is_observationally_equivalent():
    normal = _learn(noisy=True, reverse_input=False)
    reversed_input = _learn(noisy=True, reverse_input=True)

    _nw, normal_pairwise, normal_higher, normal_candidates, normal_memory = normal
    _rw, reverse_pairwise, reverse_higher, reverse_candidates, reverse_memory = (
        reversed_input
    )

    assert normal_pairwise.pattern_slices == reverse_pairwise.pattern_slices
    assert _signature(normal_higher) == _signature(reverse_higher)
    assert normal_candidates == reverse_candidates
    assert normal_memory.snapshot() == reverse_memory.snapshot()


def test_life_gate_020_clean_and_noisy_recall_contracts_remain_identical():
    clean = _learn(noisy=False)
    noisy = _learn(noisy=True)

    _cw, _cp, _ch, clean_candidates, clean_memory = clean
    _nw, _np, _nh, noisy_candidates, noisy_memory = noisy

    clean_contract = {
        (
            item.antecedent_patterns,
            item.consequence_pattern,
            item.supporting_slice_ids,
        )
        for item in clean_memory.snapshot()
    }
    noisy_contract = {
        (
            item.antecedent_patterns,
            item.consequence_pattern,
            item.supporting_slice_ids,
        )
        for item in noisy_memory.snapshot()
    }

    assert noisy_candidates == clean_candidates
    assert noisy_contract == clean_contract


def test_life_gate_020_is_deterministic_under_repeated_noisy_runs():
    a = _learn(noisy=True)
    b = _learn(noisy=True)

    _aw, pair_a, higher_a, candidates_a, memory_a = a
    _bw, pair_b, higher_b, candidates_b, memory_b = b

    assert pair_a.pattern_slices == pair_b.pattern_slices
    assert _signature(higher_a) == _signature(higher_b)
    assert candidates_a == candidates_b
    assert memory_a.snapshot() == memory_b.snapshot()
