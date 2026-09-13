from memoria_resolutiva.active_causal_experiment_v2 import InterventionOption, select_active_causal_experiment
from memoria_resolutiva.live_infinita_adapter_v2 import make_live_request
from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import (
    execute_validated_action,
    generate_valid_actions,
    possible_action_outcomes,
)
from memoria_v2_adapter import intervention_from_proposal, observer_state_addresses
from scenario_continuous_closed_loop import apply_regime_shift, build_continuous_world


def _probe(world):
    return next(item for item in generate_valid_actions(world, "nova") if item["action"] == "probe")


def _candidate_triplets(world, proposal):
    state = observer_state_addresses(world, "nova")
    next_state = state
    values = []
    for index, outcome in enumerate(possible_action_outcomes(world, proposal)):
        values.append((f"candidate-{index}", outcome, next_state))
    return tuple(values)


def _actual_candidate_id(world, proposal):
    rule_id = proposal["parameters"]["rule_id"]
    rule = next(item for item in world["rules"]["actions"] if item["rule_id"] == rule_id)
    actual = (rule["consequence_address"],)
    candidates = _candidate_triplets(world, proposal)
    return next(cid for cid, consequence, _ in candidates if consequence == actual)


def test_runtime_keeps_only_current_observation_relation_active():
    world = build_continuous_world()
    for _ in range(4):
        execution = execute_validated_action(world, _probe(world))
        world = execution.world
        active_runtime_relations = [
            relation
            for relation in world["relations"].values()
            if relation.get("status") == "active"
            and (relation.get("source") or {}).get("type") == "world-runtime"
        ]
        assert len(active_runtime_relations) == 1

    assert len(world["events"]) == 4
    assert len(world["deltas"]) == 4


def test_v2_tracks_multitick_regime_shift_without_future_leakage():
    world = build_continuous_world()
    gym = SituatedLiveCognitiveGymV2(min_independent_episodes=2, min_contiguous_support=2)

    observed = []
    steps = []
    for index in range(4):
        if index == 2:
            world = apply_regime_shift(world)

        proposal = _probe(world)
        intervention = intervention_from_proposal(proposal)
        state = observer_state_addresses(world, "nova")
        request = make_live_request(
            frame_id=f"frame-{world['current_tick']}",
            state_addresses=state,
            intervention_id=proposal["proposal_id"],
            intervention_address=intervention.intervention_address,
            candidates=_candidate_triplets(world, proposal),
            provenance="live.infinita.closed-loop",
        )
        actual_id = _actual_candidate_id(world, proposal)

        # Prediction/gym step happens before the world mutation for this tick.
        step = gym.step(request, actual_candidate_id=actual_id, learn=True)
        steps.append(step)

        execution = execute_validated_action(world, proposal)
        observed.append(execution.consequence_address)
        world = execution.world

    assert observed == ["live:effect:x", "live:effect:x", "live:effect:y", "live:effect:y"]

    # Two contiguous X observations establish X; first Y challenges but does not switch;
    # second Y establishes the new active regime. No recency weight is involved.
    assert steps[1].current_regime.active is not None
    assert steps[1].current_regime.active.consequence_addresses == ("live:effect:x",)
    assert steps[2].prior_regime.active is not None
    assert steps[2].prior_regime.active.consequence_addresses == ("live:effect:x",)
    assert steps[2].current_regime.pending is not None
    assert steps[2].current_regime.pending.consequence_addresses == ("live:effect:y",)
    assert steps[3].current_regime.active is not None
    assert steps[3].current_regime.active.consequence_addresses == ("live:effect:y",)
    assert steps[3].current_regime.switches == 1


def test_v2_active_selector_still_chooses_world_offered_probe_each_tick():
    world = build_continuous_world()
    proposal_by_address = {}
    options = []
    for proposal in generate_valid_actions(world, "nova"):
        intervention = intervention_from_proposal(proposal)
        proposal_by_address[intervention.intervention_address] = proposal
        options.append(
            InterventionOption(
                intervention_address=intervention.intervention_address,
                possible_outcomes=possible_action_outcomes(world, proposal),
                available=True,
            )
        )

    selected = select_active_causal_experiment(
        hypothesis_outcomes=(
            ("H-X", ("live:effect:x",)),
            ("H-Y", ("live:effect:y",)),
        ),
        options=tuple(options),
    )
    assert selected.active is True
    chosen = proposal_by_address[selected.intervention_address]
    assert chosen["action"] == "probe"
