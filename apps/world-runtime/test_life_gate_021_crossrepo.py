from __future__ import annotations

from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_context_recall_v2 import (
    recall_structural_context,
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
from scenario_life_gate_021 import build_life_gate_021_world


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
    world = build_life_gate_021_world(
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


def _distractor_ids(count: int = 8) -> tuple[int, ...]:
    return tuple(
        sensor_pattern_id(f"s_noise_close_{index}", "r0")
        for index in range(count)
    )


def _augment_with_close_recurrent_noise(
    rs: RealitySlice,
    *,
    episode_id: int,
    count: int,
    reverse_input: bool = False,
) -> RealitySlice:
    occurrences = list(rs.occurrences)

    # Base sensor centers are approximately d0=.01, agent=.11, context=.21,
    # consequence=.51. Distractors are recurrent and deliberately placed between
    # agent and context, within context_span of both and within simultaneous_delta
    # of one another so they act as antecedent context rather than fake consequences.
    for index, pattern in enumerate(_distractor_ids(count)):
        start = 0.168 + index * 0.008
        occurrences.append(
            Occurrence(
                pattern=pattern,
                modality=Modality.SENSOR,
                t_start=start,
                t_end=start + 0.004,
                source=920000 + index,
                provenance=720000 + episode_id,
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


def _learn(*, reverse_input: bool = False):
    pairwise = TemporalAssociator(lambda0=0.0)
    higher = None
    policy = None
    provenance = {}
    last_world = None
    episode_id = 1600

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
                higher = make_sparse_context_associator(policy, lambda0=0.0)

            rs = _augment_with_close_recurrent_noise(
                window.reality_slice,
                episode_id=episode_id,
                count=int(
                    world["rules"]["higher_order_stress"][
                        "recurring_close_distractors"
                    ]
                ),
                reverse_input=reverse_input,
            )
            pairwise.ingest(rs)
            higher.ingest(rs, pattern_support=pairwise.pattern_slices)
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


def _true_candidate_keys():
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


def test_life_gate_021_distractors_are_recurrent_and_temporally_local():
    _world, pairwise, _higher, _candidates, _memory = _learn()

    distractors = _distractor_ids()
    assert len(pairwise.pattern_slices) == 15
    assert all(pairwise.pattern_slices[pattern] == 20 for pattern in distractors)


def test_life_gate_021_close_recurrent_noise_expands_index_but_not_admission():
    _world, _pairwise, higher, candidates, memory = _learn()

    assert len(higher.links) == 128
    assert len(candidates) == 4
    assert len(memory.snapshot()) == 4
    assert {
        (candidate.antecedent_patterns, candidate.consequence_pattern)
        for candidate in candidates
    } == _true_candidate_keys()

    assert len(candidates) / len(higher.links) == 0.03125


def test_life_gate_021_false_recurrent_contexts_fail_context_reliability():
    _world, _pairwise, higher, candidates, _memory = _learn()

    admitted_keys = {
        (
            candidate.antecedent_patterns[0],
            candidate.antecedent_patterns[1],
            candidate.consequence_pattern,
        )
        for candidate in candidates
    }
    false_links = [
        link
        for key, link in higher.links.items()
        if key not in admitted_keys
    ]

    assert len(false_links) == 124
    assert max(higher.context_reliability(link) for link in false_links) < 0.60
    assert min(higher.context_reliability(link) for link in false_links) > 0.0


def test_life_gate_021_no_distractor_enters_admitted_context_or_memoria():
    _world, _pairwise, _higher, candidates, memory = _learn()

    distractors = set(_distractor_ids())
    admitted_patterns = {
        pattern
        for candidate in candidates
        for pattern in (
            *candidate.antecedent_patterns,
            candidate.consequence_pattern,
        )
    }
    remembered_patterns = {
        int(address.rsplit(":", 1)[-1])
        for item in memory.snapshot()
        for address in (
            *item.antecedent_patterns,
            item.consequence_pattern,
        )
    }

    assert admitted_patterns.isdisjoint(distractors)
    assert remembered_patterns.isdisjoint(distractors)


def test_life_gate_021_false_exact_context_recall_is_empty():
    _world, _pairwise, _higher, _candidates, memory = _learn()

    distractor = _address(_distractor_ids()[0])
    a0 = _address(sensor_pattern_id(AGENT_SENSOR, "a0"))
    recall = recall_structural_context(
        memory,
        (a0, distractor),
        min_independent_slices=3,
    )

    assert recall.neighbors == ()


def test_life_gate_021_true_exact_context_recall_still_resolves_xor():
    _world, _pairwise, _higher, _candidates, memory = _learn()

    table = {
        ("a0", "c0"): "d1",
        ("a0", "c1"): "d2",
        ("a1", "c0"): "d2",
        ("a1", "c1"): "d1",
    }
    for (agent_band, context_band), consequence_band in table.items():
        recall = recall_structural_context(
            memory,
            (
                _address(sensor_pattern_id(AGENT_SENSOR, agent_band)),
                _address(sensor_pattern_id(CONTEXT_SENSOR, context_band)),
            ),
            min_independent_slices=3,
        )
        assert len(recall.neighbors) == 1
        assert recall.neighbors[0].consequence_pattern == _address(
            sensor_pattern_id(FLOW_SENSOR, consequence_band)
        )


def test_life_gate_021_reversed_occurrence_input_is_equivalent():
    normal = _learn(reverse_input=False)
    reversed_input = _learn(reverse_input=True)

    _nw, npair, nhigher, ncandidates, nmemory = normal
    _rw, rpair, rhigher, rcandidates, rmemory = reversed_input

    assert npair.pattern_slices == rpair.pattern_slices
    assert _signature(nhigher) == _signature(rhigher)
    assert ncandidates == rcandidates
    assert nmemory.snapshot() == rmemory.snapshot()


def test_life_gate_021_is_deterministic():
    a = _learn()
    b = _learn()

    _aw, apair, ahigher, acandidates, amemory = a
    _bw, bpair, bhigher, bcandidates, bmemory = b

    assert apair.pattern_slices == bpair.pattern_slices
    assert _signature(ahigher) == _signature(bhigher)
    assert acandidates == bcandidates
    assert amemory.snapshot() == bmemory.snapshot()
