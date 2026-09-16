from __future__ import annotations

from memoria_resolutiva.active_causal_experiment_v2 import InterventionOption
from memoria_resolutiva.active_causal_loop_v2 import CausalHypothesis, run_active_causal_loop

from closed_loop_runtime import (
    execute_validated_action,
    generate_valid_actions,
    offered_outcomes,
)
from memoria_v2_adapter import intervention_from_proposal


def _world() -> dict:
    return {
        "world_id": "closed-loop-test",
        "current_tick": 10,
        "current_version": 10,
        "entities": {
            "nova": {
                "entity_id": "nova",
                "status": "active",
                "components": {"transform": {"region_id": "r1"}},
            },
            "fire": {
                "entity_id": "fire",
                "status": "active",
                "components": {"transform": {"region_id": "r1"}},
            },
        },
        "relations": {},
        "rules": {
            "actions": [
                {
                    "rule_id": "rule_probe",
                    "actor": "nova",
                    "action": "probe",
                    "target": "fire",
                    "possible_consequence_addresses": ["live:effect:x", "live:effect:y"],
                    "consequence_address": "live:effect:y",
                },
                {
                    "rule_id": "rule_wait",
                    "actor": "nova",
                    "action": "wait",
                    "target": None,
                    "possible_consequence_addresses": ["live:outcome:no-structural-change"],
                    "consequence_address": "live:outcome:no-structural-change",
                },
            ]
        },
        "events": {},
        "deltas": {},
        "versions": {"10": {"parent_version": 9, "delta_id": None}},
    }


def test_closed_loop_world_rules_to_v2_choice_to_delta_event():
    world = _world()
    proposals = generate_valid_actions(world, "nova")
    assert len(proposals) == 2

    outcome_map = offered_outcomes(world, proposals)
    by_address = {
        intervention_from_proposal(proposal).intervention_address: proposal
        for proposal in proposals
    }
    options = tuple(
        InterventionOption(
            intervention_address=address,
            possible_outcomes=outcome_map[proposal["proposal_id"]],
            available=True,
        )
        for address, proposal in sorted(by_address.items())
    )

    hypotheses = (
        CausalHypothesis("H-X", ("live:effect:x",)),
        CausalHypothesis("H-Y", ("live:effect:y",)),
    )
    executions = []

    def options_provider(_active):
        return options

    def execute_intervention(address: str):
        proposal = by_address[address]
        execution = execute_validated_action(world, proposal)
        executions.append(execution)
        return (execution.consequence_address,)

    result = run_active_causal_loop(
        hypotheses=hypotheses,
        options_provider=options_provider,
        execute_intervention=execute_intervention,
        max_steps=2,
    )

    assert result.resolved is True
    assert result.surviving_hypotheses == ("H-Y",)
    assert len(executions) == 1

    execution = executions[0]
    assert execution.proposal["action"] == "probe"
    assert execution.consequence_address == "live:effect:y"
    assert execution.delta["base_version"] == 10
    assert execution.delta["result_version"] == 11
    assert execution.delta["tick_id"] == 11
    assert execution.event["cause"]["proposal_id"] == execution.proposal["proposal_id"]
    assert execution.event["delta_id"] == execution.delta["delta_id"]
    assert execution.world["current_tick"] == 11
    assert execution.world["current_version"] == 11
    assert execution.delta["delta_id"] in execution.world["deltas"]
    assert execution.event["event_id"] in execution.world["events"]


def test_runtime_rejects_stale_proposal_after_world_advances():
    world = _world()
    proposal = next(item for item in generate_valid_actions(world, "nova") if item["action"] == "probe")
    execution = execute_validated_action(world, proposal)

    try:
        execute_validated_action(execution.world, proposal)
    except ValueError as exc:
        assert "tick" in str(exc)
    else:
        raise AssertionError("stale proposal must be rejected")


def test_inactive_actor_receives_no_actions():
    world = _world()
    world["entities"]["nova"]["status"] = "inactive"
    assert generate_valid_actions(world, "nova") == ()
