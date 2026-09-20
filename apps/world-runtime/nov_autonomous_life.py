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
    generate_valid_actions,
    possible_action_outcomes,
    pre_action_cognitive_world,
)
from memoria_v2_adapter import intervention_from_proposal, observer_state_addresses
from nov_need_scheduler import (
    NeedActionDecision,
    NeedState,
    advance_needs,
    relieve_need,
    select_need_action,
)


@dataclass(frozen=True, slots=True)
class AutonomousDecision:
    mode: str
    proposal: dict[str, Any]
    request: LiveWorldStateRequest
    evaluated_needs: NeedState
    need_decision: NeedActionDecision | None
    diagnostics: dict[str, dict[str, Any]]


def request_for_proposal(
    world: dict[str, Any],
    proposal: dict[str, Any],
    *,
    observer_id: str = "nova",
) -> LiveWorldStateRequest:
    cognitive_world = pre_action_cognitive_world(world, observer_id)
    state = observer_state_addresses(cognitive_world, observer_id)
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
        frame_id=f"autonomous-{world['current_tick']}-{proposal['proposal_id']}",
        state_addresses=state,
        intervention_id=proposal["proposal_id"],
        intervention_address=intervention.intervention_address,
        candidates=candidates,
        provenance="live.infinita.autonomous-life-v0",
    )


def prediction_for_request(
    gym: SituatedLiveCognitiveGymV2,
    request: LiveWorldStateRequest,
):
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


def choose_autonomous_action(
    *,
    gym: SituatedLiveCognitiveGymV2,
    world: dict[str, Any],
    needs: NeedState,
    observer_id: str = "nova",
) -> AutonomousDecision:
    """Curiosity first when unresolved; otherwise choose by local need pressure.

    Memoria.ia contributes only prediction/uncertainty. Need state never enters the
    cognitive request and cannot change World State. Both paths select only proposals
    already emitted by the world runtime.
    """
    proposals = generate_valid_actions(world, observer_id)
    if not proposals:
        raise ValueError("observer has no valid world actions")

    evaluated_needs = advance_needs(
        needs,
        tick_id=int(world.get("current_tick", needs.tick_id)),
    )

    by_address: dict[str, tuple[dict[str, Any], LiveWorldStateRequest]] = {}
    options: list[InterventionOption] = []
    unresolved_outcomes: list[tuple[str, ...]] = []
    diagnostics: dict[str, dict[str, Any]] = {}

    for proposal in proposals:
        request = request_for_proposal(world, proposal, observer_id=observer_id)
        key, prior, effective = prediction_for_request(gym, request)
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
        return AutonomousDecision(
            mode="curiosity",
            proposal=proposal,
            request=request,
            evaluated_needs=evaluated_needs,
            need_decision=None,
            diagnostics=diagnostics,
        )

    need_decision = select_need_action(
        world=world,
        proposals=proposals,
        needs=evaluated_needs,
    )
    if need_decision is None:
        raise ValueError("no serviceable autonomous need for available world actions")

    proposal = need_decision.proposal
    request = request_for_proposal(world, proposal, observer_id=observer_id)
    return AutonomousDecision(
        mode="need",
        proposal=proposal,
        request=request,
        evaluated_needs=evaluated_needs,
        need_decision=need_decision,
        diagnostics=diagnostics,
    )


def needs_after_committed_action(
    *,
    decision: AutonomousDecision,
    result_tick: int,
) -> NeedState:
    """Advance local time and relieve only the need actually selected by scheduler."""
    advanced = advance_needs(decision.evaluated_needs, tick_id=result_tick)
    if decision.mode != "need" or decision.need_decision is None:
        return advanced
    return relieve_need(advanced, decision.need_decision.need_id)
