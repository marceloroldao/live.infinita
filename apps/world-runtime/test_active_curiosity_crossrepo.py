from memoria_resolutiva.active_causal_experiment_v2 import InterventionOption
from memoria_resolutiva.active_causal_loop_v2 import CausalHypothesis, run_active_causal_loop

from scenario_active_curiosity import build_active_curiosity_scenario


def test_v2_selects_world_offered_discriminative_intervention_and_resolves():
    scenario = build_active_curiosity_scenario()

    hypotheses = tuple(
        CausalHypothesis(hypothesis_id, expected_outcome)
        for hypothesis_id, expected_outcome in scenario["hypotheses"]
    )
    options = tuple(
        InterventionOption(
            intervention_address=item.intervention_address,
            possible_outcomes=item.possible_outcomes,
            available=True,
        )
        for item in scenario["options"]
    )
    offered_addresses = {item.intervention_address for item in scenario["options"]}
    executed: list[str] = []

    def options_provider(_active):
        return options

    def execute_intervention(address: str):
        assert address in offered_addresses
        executed.append(address)
        return scenario["world_results"][address]

    result = run_active_causal_loop(
        hypotheses=hypotheses,
        options_provider=options_provider,
        execute_intervention=execute_intervention,
        max_steps=2,
    )

    assert result.resolved is True
    assert result.exhausted is False
    assert result.surviving_hypotheses == (scenario["expected_survivor"],)
    assert len(result.steps) == 1
    assert result.steps[0].intervention_address == scenario["expected_selected_intervention"]
    assert executed == [scenario["expected_selected_intervention"]]
    assert result.reason == "ambiguity-resolved-by-active-experiment"


def test_v2_never_selects_neutral_option_when_it_cannot_separate_hypotheses():
    scenario = build_active_curiosity_scenario()
    neutral = next(item for item in scenario["options"] if item.proposal_id == "proposal-wait")

    hypotheses = tuple(
        CausalHypothesis(hypothesis_id, expected_outcome)
        for hypothesis_id, expected_outcome in scenario["hypotheses"]
    )
    options = tuple(
        InterventionOption(item.intervention_address, item.possible_outcomes, True)
        for item in scenario["options"]
    )

    result = run_active_causal_loop(
        hypotheses=hypotheses,
        options_provider=lambda _active: options,
        execute_intervention=lambda address: scenario["world_results"][address],
        max_steps=1,
    )

    assert result.steps[0].intervention_address != neutral.intervention_address
