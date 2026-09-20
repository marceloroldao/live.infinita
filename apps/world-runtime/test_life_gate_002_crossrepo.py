from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import (
    execute_validated_action,
    generate_valid_actions,
    pre_action_cognitive_world,
)
from memoria_v2_adapter import observer_state_addresses
from nov_autonomous_life import (
    choose_autonomous_action,
    needs_after_committed_action,
)
from scenario_life_gate_001 import advance_ambient_ticks, relocate_nova
from scenario_life_gate_002 import build_life_gate_002_world, initial_nov_needs


def _actual_candidate_id(request, consequence_address: str) -> str:
    consequence = (consequence_address,)
    return next(
        candidate.candidate_id
        for candidate in request.candidates
        if candidate.consequence_addresses == consequence
    )


def _commit_and_learn(gym, world, needs, decision):
    execution = execute_validated_action(world, decision.proposal)
    actual_id = _actual_candidate_id(decision.request, execution.consequence_address)
    step = gym.step(decision.request, actual_candidate_id=actual_id, learn=True)
    needs = needs_after_committed_action(
        decision=decision,
        result_tick=execution.world["current_tick"],
    )
    return execution.world, needs, step


def _establish_known_source():
    world = build_life_gate_002_world()
    needs = initial_nov_needs(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    discovery = []
    steps = []
    for _ in range(2):
        decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
        discovery.append(decision)
        assert decision.mode == "curiosity"
        assert decision.proposal["action"] == "probe"
        world, needs, step = _commit_and_learn(gym, world, needs, decision)
        steps.append(step)

    assert steps[-1].current_regime.active is not None
    return world, needs, gym, tuple(discovery), tuple(steps)


def _return_after_absence(world):
    world = relocate_nova(world, "forest_far", near_source=False)
    world = advance_ambient_ticks(world, 16)
    world = relocate_nova(world, "forest_source_edge", near_source=True)
    return world


def _run_gate_signature():
    world, needs, gym, discovery, steps = _establish_known_source()
    established_key = steps[-1].context_key
    world = _return_after_absence(world)

    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes
    events_before = tuple(sorted(world["events"]))
    deltas_before = tuple(sorted(world["deltas"]))

    return_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    probe_diag = next(
        item
        for item in return_decision.diagnostics.values()
        if item["action"] == "probe"
    )

    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before
    assert tuple(sorted(world["events"])) == events_before
    assert tuple(sorted(world["deltas"])) == deltas_before

    walk_execution = execute_validated_action(world, return_decision.proposal)
    needs_after_walk = needs_after_committed_action(
        decision=return_decision,
        result_tick=walk_execution.world["current_tick"],
    )
    world = walk_execution.world

    rest_decision = choose_autonomous_action(
        gym=gym,
        world=world,
        needs=needs_after_walk,
    )

    return (
        tuple((item.mode, item.proposal["action"]) for item in discovery),
        established_key,
        probe_diag["context_key"],
        probe_diag["effective_prediction"].reason,
        probe_diag["effective_prediction"].resolved,
        return_decision.mode,
        return_decision.need_decision.need_id if return_decision.need_decision else None,
        return_decision.proposal["action"],
        return_decision.evaluated_needs.pressure("roam"),
        return_decision.evaluated_needs.pressure("recover"),
        needs_after_walk.pressure("roam"),
        needs_after_walk.pressure("recover"),
        rest_decision.mode,
        rest_decision.need_decision.need_id if rest_decision.need_decision else None,
        rest_decision.proposal["action"],
        tuple(rest_decision.request.state.state_addresses),
        len(memory_before),
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_002_curiosity_preempts_needs_only_while_context_is_unresolved():
    world = build_life_gate_002_world()
    needs = initial_nov_needs(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    assert needs.pressure("roam") > needs.pressure("recover")
    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)

    assert decision.mode == "curiosity"
    assert decision.need_decision is None
    assert decision.proposal["action"] == "probe"


def test_life_gate_002_known_context_hands_control_to_need_scheduler():
    signature = _run_gate_signature()
    (
        discovery,
        established_key,
        returned_key,
        prediction_reason,
        prediction_resolved,
        return_mode,
        return_need,
        return_action,
        roam_before_walk,
        recover_before_walk,
        roam_after_walk,
        recover_after_walk,
        second_mode,
        second_need,
        second_action,
        _state_addresses,
        episode_count,
        _tick,
        _version,
    ) = signature

    assert discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert episode_count == 2
    assert returned_key == established_key
    assert prediction_resolved is True
    assert prediction_reason == "active-temporal-regime"

    # On return the known context no longer consumes exploratory attention.
    assert return_mode == "need"
    assert return_need == "roam"
    assert return_action == "walk"
    assert roam_before_walk > recover_before_walk

    # A committed walk relieves roam; the still-growing recovery need then wins.
    assert roam_after_walk == 0
    assert recover_after_walk > 0
    assert second_mode == "need"
    assert second_need == "recover"
    assert second_action == "rest"


def test_life_gate_002_need_selection_is_read_only_and_world_bounded():
    world, needs, gym, _, _ = _establish_known_source()
    world = _return_after_absence(world)

    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes
    events_before = tuple(sorted(world["events"]))
    deltas_before = tuple(sorted(world["deltas"]))
    version_before = world["current_version"]
    tick_before = world["current_tick"]

    valid_proposals = {
        item["proposal_id"]: item
        for item in generate_valid_actions(world, "nova")
    }
    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)

    assert decision.mode == "need"
    assert decision.proposal["proposal_id"] in valid_proposals
    assert decision.proposal == valid_proposals[decision.proposal["proposal_id"]]
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before
    assert tuple(sorted(world["events"])) == events_before
    assert tuple(sorted(world["deltas"])) == deltas_before
    assert world["current_version"] == version_before
    assert world["current_tick"] == tick_before


def test_life_gate_002_needs_do_not_leak_into_memoria_state_addresses():
    signature = _run_gate_signature()
    state_addresses = signature[15]

    assert state_addresses
    assert all("roam" not in address for address in state_addresses)
    assert all("recover" not in address for address in state_addresses)
    assert all("need:" not in address for address in state_addresses)


def test_life_gate_002_memory_context_survives_world_time_without_need_coupling():
    world, needs, gym, _, steps = _establish_known_source()
    initial_cognitive_state = observer_state_addresses(
        pre_action_cognitive_world(world, "nova"),
        "nova",
    )
    established_key = steps[-1].context_key

    world = _return_after_absence(world)
    return_cognitive_state = observer_state_addresses(
        pre_action_cognitive_world(world, "nova"),
        "nova",
    )
    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    probe_diag = next(
        item for item in decision.diagnostics.values()
        if item["action"] == "probe"
    )

    assert return_cognitive_state == initial_cognitive_state
    assert probe_diag["context_key"] == established_key
    assert probe_diag["prior_regime"].active is not None
    assert decision.evaluated_needs.tick_id == world["current_tick"]


def test_life_gate_002_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
