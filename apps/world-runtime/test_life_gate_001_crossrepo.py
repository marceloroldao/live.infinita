from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memoria_resolutiva.active_causal_experiment_v2 import (
    InterventionOption,
    select_active_causal_experiment,
)
from memoria_resolutiva.live_infinita_adapter_v2 import (
    LiveWorldStateRequest,
    make_live_request,
    to_world_state_candidates,
)
from memoria_resolutiva.situated_contextual_regime_v2 import situated_context_key
from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
from memoria_resolutiva.temporal_regime_state_v2 import constrain_prediction_to_active_regime
from memoria_resolutiva.world_state_candidate_resolution_v2 import (
    resolve_world_state_candidates,
)

from closed_loop_runtime import (
    execute_validated_action,
    generate_valid_actions,
    possible_action_outcomes,
    pre_action_cognitive_world,
)
from memoria_v2_adapter import intervention_from_proposal, observer_state_addresses
from scenario_life_gate_001 import (
    advance_ambient_ticks,
    build_life_gate_world,
    relocate_nova,
)


@dataclass(frozen=True, slots=True)
class LifeDecision:
    mode: str
    proposal: dict[str, Any]
    request: LiveWorldStateRequest
    diagnostics: dict[str, dict[str, Any]]


def _request_for(world: dict, proposal: dict) -> LiveWorldStateRequest:
    cognitive_world = pre_action_cognitive_world(world, "nova")
    state = observer_state_addresses(cognitive_world, "nova")
    intervention = intervention_from_proposal(proposal)
    candidates = tuple(
        (
            f"candidate-{index}",
            outcome,
            state,
        )
        for index, outcome in enumerate(possible_action_outcomes(world, proposal))
    )
    return make_live_request(
        frame_id=f"life-gate-{world['current_tick']}-{proposal['proposal_id']}",
        state_addresses=state,
        intervention_id=proposal["proposal_id"],
        intervention_address=intervention.intervention_address,
        candidates=candidates,
        provenance="live.infinita.life-gate-001",
    )


def _prediction(gym: SituatedLiveCognitiveGymV2, request: LiveWorldStateRequest):
    candidates = to_world_state_candidates(request)
    key = situated_context_key(
        request.state.state_addresses,
        request.intervention.address,
    )
    prior = gym.regimes.get(key)
    base = resolve_world_state_candidates(
        gym.memory,
        request.state.state_addresses,
        request.intervention.address,
        candidates,
        min_independent_episodes=gym.min_independent_episodes,
    )
    effective = constrain_prediction_to_active_regime(base, prior)
    return key, prior, effective


def _choose_life_action(gym: SituatedLiveCognitiveGymV2, world: dict) -> LifeDecision:
    """Let memory gate curiosity without letting cognition invent world actions.

    Multi-outcome interventions remain curiosity candidates only while their
    consequence is unresolved. Once V2 recognizes the situated regime, curiosity
    no longer preempts the world's deterministic baseline action.
    """
    proposals = generate_valid_actions(world, "nova")
    if not proposals:
        raise AssertionError("Life Gate requires at least one valid world action")

    by_address: dict[str, tuple[dict, LiveWorldStateRequest]] = {}
    options: list[InterventionOption] = []
    unresolved_outcomes: list[tuple[str, ...]] = []
    diagnostics: dict[str, dict[str, Any]] = {}

    for proposal in proposals:
        request = _request_for(world, proposal)
        key, prior, effective = _prediction(gym, request)
        outcomes = tuple(tuple(item) for item in possible_action_outcomes(world, proposal))
        by_address[request.intervention.address] = (proposal, request)
        diagnostics[proposal["proposal_id"]] = {
            "action": proposal["action"],
            "context_key": key,
            "prior_regime": prior,
            "effective_prediction": effective,
            "possible_outcomes": outcomes,
        }

        distinct = tuple(dict.fromkeys(outcomes))
        if not effective.resolved and len(distinct) >= 2:
            options.append(
                InterventionOption(
                    intervention_address=request.intervention.address,
                    possible_outcomes=distinct,
                    available=True,
                )
            )
            unresolved_outcomes.extend(distinct)

    hypotheses = tuple(
        (f"H-{index:02d}", outcome)
        for index, outcome in enumerate(sorted(set(unresolved_outcomes)))
    )
    experiment = select_active_causal_experiment(
        hypothesis_outcomes=hypotheses,
        options=tuple(options),
    )

    if experiment.active and experiment.intervention_address is not None:
        proposal, request = by_address[experiment.intervention_address]
        return LifeDecision("curiosity", proposal, request, diagnostics)

    baseline = []
    for address, (proposal, request) in by_address.items():
        outcomes = tuple(dict.fromkeys(possible_action_outcomes(world, proposal)))
        if len(outcomes) == 1:
            baseline.append((address, proposal, request))
    if not baseline:
        raise AssertionError("no deterministic baseline action is available")

    _, proposal, request = sorted(baseline, key=lambda item: item[0])[0]
    return LifeDecision("baseline", proposal, request, diagnostics)


def _actual_candidate_id(request: LiveWorldStateRequest, consequence_address: str) -> str:
    consequence = (consequence_address,)
    return next(
        candidate.candidate_id
        for candidate in request.candidates
        if candidate.consequence_addresses == consequence
    )


def _discover_source_twice(gym: SituatedLiveCognitiveGymV2, world: dict):
    steps = []
    decisions = []
    for _ in range(2):
        decision = _choose_life_action(gym, world)
        assert decision.mode == "curiosity"
        assert decision.proposal["action"] == "probe"

        execution = execute_validated_action(world, decision.proposal)
        actual_id = _actual_candidate_id(decision.request, execution.consequence_address)
        step = gym.step(decision.request, actual_candidate_id=actual_id, learn=True)
        decisions.append(decision)
        steps.append(step)
        world = execution.world
    return world, tuple(decisions), tuple(steps)


def _run_gate_signature():
    world = build_life_gate_world()
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    initial_state = observer_state_addresses(pre_action_cognitive_world(world, "nova"), "nova")
    world, discovery_decisions, discovery_steps = _discover_source_twice(gym, world)

    established = discovery_steps[-1]
    assert established.current_regime.active is not None

    world = relocate_nova(world, "forest_far", near_source=False)
    world = advance_ambient_ticks(world, 16)
    world = relocate_nova(world, "forest_source_edge", near_source=True)

    episodes_before = gym.memory.snapshot()
    regimes_before = gym.regimes
    return_state = observer_state_addresses(pre_action_cognitive_world(world, "nova"), "nova")
    return_decision = _choose_life_action(gym, world)

    assert gym.memory.snapshot() == episodes_before
    assert gym.regimes == regimes_before

    probe_diag = next(
        item
        for item in return_decision.diagnostics.values()
        if item["action"] == "probe"
    )
    effective = probe_diag["effective_prediction"]
    prior = probe_diag["prior_regime"]

    return (
        tuple((item.mode, item.proposal["action"]) for item in discovery_decisions),
        established.context_key,
        probe_diag["context_key"],
        initial_state,
        return_state,
        prior,
        effective.reason,
        effective.resolved,
        effective.resolved_candidate.candidate_id if effective.resolved_candidate else None,
        return_decision.mode,
        return_decision.proposal["action"],
        len(episodes_before),
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_001_memory_changes_novas_behavior_after_return():
    signature = _run_gate_signature()
    (
        discovery,
        established_key,
        returned_key,
        initial_state,
        return_state,
        prior,
        prediction_reason,
        prediction_resolved,
        resolved_candidate_id,
        return_mode,
        return_action,
        episode_count,
        _tick,
        _version,
    ) = signature

    assert discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert episode_count == 2

    # The spatial/cognitive context is recovered after leaving and spending time away.
    assert return_state == initial_state
    assert returned_key == established_key
    assert prior.active is not None

    # Recognition happens before a new observation at the returned location.
    assert prediction_resolved is True
    assert resolved_candidate_id == "candidate-0"
    assert prediction_reason == "active-temporal-regime"

    # Curiosity no longer needs to probe the already-established situated regime.
    assert return_mode == "baseline"
    assert return_action == "continue"


def test_life_gate_001_return_decision_is_read_only_until_world_executes():
    world = build_life_gate_world()
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )
    world, _, _ = _discover_source_twice(gym, world)
    world = relocate_nova(world, "forest_far", near_source=False)
    world = advance_ambient_ticks(world, 16)
    world = relocate_nova(world, "forest_source_edge", near_source=True)

    episodes_before = gym.memory.snapshot()
    regimes_before = gym.regimes
    events_before = tuple(sorted(world["events"]))
    deltas_before = tuple(sorted(world["deltas"]))
    version_before = world["current_version"]
    tick_before = world["current_tick"]

    decision = _choose_life_action(gym, world)

    assert decision.mode == "baseline"
    assert decision.proposal["action"] == "continue"
    assert gym.memory.snapshot() == episodes_before
    assert gym.regimes == regimes_before
    assert tuple(sorted(world["events"])) == events_before
    assert tuple(sorted(world["deltas"])) == deltas_before
    assert world["current_version"] == version_before
    assert world["current_tick"] == tick_before

    execution = execute_validated_action(world, decision.proposal)
    assert execution.event["action"] == "continue"
    assert execution.world["current_tick"] == tick_before + 1
    assert execution.world["current_version"] == version_before + 1


def test_life_gate_001_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
