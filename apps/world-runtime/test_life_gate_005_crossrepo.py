from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import execute_validated_action, generate_valid_actions
from distributed_environment_runtime import advance_distributed_environmental_agents
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
from scenario_life_gate_005 import build_life_gate_005_world, initial_nov_needs_005
from spatial_runtime import relocate_entity


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


def _distribution(world):
    return world["entities"]["water_01"]["components"]["environmental_distribution"]


def _establish_spring_experience():
    world = build_life_gate_005_world()
    needs = initial_nov_needs_005(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    decisions = []
    steps = []
    for _ in range(2):
        decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
        assert decision.mode == "curiosity"
        assert decision.proposal["action"] == "probe"
        assert decision.proposal["target"] == "water_01"
        assert "live:entity:water_01" in decision.request.state.state_addresses
        world, needs, step = _commit_and_learn(gym, world, needs, decision)
        decisions.append(decision)
        steps.append(step)

    assert steps[-1].current_regime.active is not None
    return world, needs, gym, tuple(decisions), tuple(steps)


def _run_gate_signature():
    world, needs, gym, discovery, spring_steps = _establish_spring_experience()
    spring_key = spring_steps[-1].context_key

    memory_before_flow = gym.memory.snapshot()
    regimes_before_flow = gym.regimes

    first_tick = advance_distributed_environmental_agents(world, ticks=1)[0]
    world = first_tick.world

    assert gym.memory.snapshot() == memory_before_flow
    assert gym.regimes == regimes_before_flow
    assert _distribution(world)["by_region"] == {
        "channel": 40,
        "hollow": 30,
        "spring": 20,
    }

    # Water is still present in spring, so the known situated context remains known.
    spring_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    spring_probe_diag = next(
        value
        for value in spring_decision.diagnostics.values()
        if value["action"] == "probe"
    )
    assert spring_probe_diag["context_key"] == spring_key
    assert spring_probe_diag["effective_prediction"].resolved is True
    assert spring_decision.mode == "need"

    # The same distributed Water agent is simultaneously present in channel.
    world = relocate_entity(world, "nova", "channel")
    channel_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert channel_decision.mode == "curiosity"
    assert channel_decision.proposal["action"] == "probe"
    assert "live:entity:water_01" in channel_decision.request.state.state_addresses

    hidden = "|".join(channel_decision.request.state.state_addresses)
    for value in (
        "environmental_distribution",
        "initial_total",
        "evaporated_total",
        "by_region",
    ):
        assert value not in hidden

    channel_probe_diag = next(
        value
        for value in channel_decision.diagnostics.values()
        if value["action"] == "probe"
    )
    channel_prior = channel_probe_diag["prior_regime"]
    channel_prediction = channel_probe_diag["effective_prediction"]

    world, needs, channel_step = _commit_and_learn(
        gym,
        world,
        needs,
        channel_decision,
    )
    memory_after_channel_probe = gym.memory.snapshot()

    second_tick = advance_distributed_environmental_agents(world, ticks=1)[0]
    world = second_tick.world

    assert gym.memory.snapshot() == memory_after_channel_probe
    distribution = _distribution(world)
    assert distribution["by_region"] == {
        "basin": 37,
        "channel": 10,
        "hollow": 15,
        "spring": 10,
    }
    assert distribution["evaporated_total"] == 28
    assert sum(distribution["by_region"].values()) + distribution["evaporated_total"] == 100

    # Basin now contains quantity created by concurrent channel+hollow flows.
    world = relocate_entity(world, "nova", "basin")
    basin_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in basin_actions
    basin_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert basin_decision.mode == "curiosity"
    assert "live:entity:water_01" in basin_decision.request.state.state_addresses

    return (
        tuple((item.mode, item.proposal["action"]) for item in discovery),
        spring_key,
        spring_probe_diag["context_key"],
        spring_decision.mode,
        spring_decision.proposal["action"],
        channel_probe_diag["context_key"],
        channel_prior.active,
        channel_prediction.ambiguous,
        channel_prediction.reason,
        channel_step.current_regime.active,
        channel_step.current_regime.pending is not None,
        tuple(sorted(distribution["by_region"].items())),
        distribution["evaporated_total"],
        tuple(
            (
                balance["region_id"],
                balance["before"],
                balance["retained"],
                balance["transferred"],
                balance["evaporated"],
            )
            for balance in second_tick.balances
        ),
        basin_decision.mode,
        basin_decision.proposal["action"],
        len(gym.memory.snapshot()),
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_005_distributed_flow_does_not_write_memoria():
    world, _needs, gym, _discovery, _steps = _establish_spring_experience()
    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes

    tick = advance_distributed_environmental_agents(world, ticks=1)[0]

    assert tick.balances
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before
    assert _distribution(tick.world)["by_region"] == {
        "channel": 40,
        "hollow": 30,
        "spring": 20,
    }


def test_life_gate_005_partial_retention_preserves_known_spring_context():
    world, needs, gym, _discovery, steps = _establish_spring_experience()
    spring_key = steps[-1].context_key
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    probe_diag = next(
        value
        for value in decision.diagnostics.values()
        if value["action"] == "probe"
    )

    assert probe_diag["context_key"] == spring_key
    assert probe_diag["prior_regime"].active is not None
    assert probe_diag["effective_prediction"].resolved is True
    assert decision.mode == "need"


def test_life_gate_005_same_water_agent_is_observable_in_multiple_regions():
    world, needs, gym, _discovery, _steps = _establish_spring_experience()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world

    for region_id in ("spring", "channel", "hollow"):
        moved = relocate_entity(world, "nova", region_id)
        actions = {item["action"] for item in generate_valid_actions(moved, "nova")}
        assert "probe" in actions

        decision = choose_autonomous_action(gym=gym, world=moved, needs=needs)
        assert "live:entity:water_01" in decision.request.state.state_addresses


def test_life_gate_005_exact_quantity_is_hidden_from_memoria():
    world, needs, gym, _discovery, _steps = _establish_spring_experience()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = relocate_entity(world, "nova", "channel")

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    serialized = "|".join(decision.request.state.state_addresses)

    for hidden in (
        "environmental_distribution",
        "initial_total",
        "evaporated_total",
        "by_region",
    ):
        assert hidden not in serialized


def test_life_gate_005_concurrent_flow_reaches_basin_with_exact_conservation():
    world = build_life_gate_005_world()
    ticks = advance_distributed_environmental_agents(world, ticks=2)
    final = _distribution(ticks[-1].world)

    assert final["by_region"] == {
        "basin": 37,
        "channel": 10,
        "hollow": 15,
        "spring": 10,
    }
    assert final["evaporated_total"] == 28
    assert sum(final["by_region"].values()) + final["evaporated_total"] == 100


def test_life_gate_005_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
