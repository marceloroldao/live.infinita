from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import execute_validated_action, generate_valid_actions
from environmental_agent_runtime import advance_environmental_agents
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
from scenario_life_gate_003 import build_life_gate_003_world, initial_nov_needs_003
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


def _water_region(world):
    return world["entities"]["water_01"]["components"]["transform"]["region_id"]


def _trace_regions(world):
    return tuple(
        sorted(
            entity["components"]["transform"]["region_id"]
            for entity in world["entities"].values()
            if entity.get("class") == "environment_trace"
        )
    )


def _establish_spring_experience():
    world = build_life_gate_003_world()
    needs = initial_nov_needs_003(world)
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

    memory_before_water_moves = gym.memory.snapshot()
    regimes_before_water_moves = gym.regimes
    action_events_before = sum(
        1 for event in world["events"].values()
        if event.get("type") == "action_committed"
    )

    env_ticks = advance_environmental_agents(world, ticks=2)
    world = env_ticks[-1].world

    assert gym.memory.snapshot() == memory_before_water_moves
    assert gym.regimes == regimes_before_water_moves
    assert _water_region(world) == "stream"
    assert sum(
        1 for event in world["events"].values()
        if event.get("type") == "action_committed"
    ) == action_events_before

    old_region_actions = generate_valid_actions(world, "nova")
    assert all(item["action"] != "probe" for item in old_region_actions)
    old_region_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert old_region_decision.mode == "need"
    assert "live:entity:water_01" not in old_region_decision.request.state.state_addresses

    world = relocate_entity(world, "nova", "stream")

    stream_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert stream_decision.mode == "curiosity"
    assert stream_decision.proposal["action"] == "probe"
    assert stream_decision.proposal["target"] == "water_01"
    assert "live:entity:water_01" in stream_decision.request.state.state_addresses

    probe_diag = next(
        value
        for value in stream_decision.diagnostics.values()
        if value["action"] == "probe"
    )
    stream_prior = probe_diag["prior_regime"]
    stream_prediction = probe_diag["effective_prediction"]

    world, needs, stream_step = _commit_and_learn(
        gym,
        world,
        needs,
        stream_decision,
    )

    memory_after_stream_probe = gym.memory.snapshot()
    env_to_basin = advance_environmental_agents(world, ticks=1)[0]
    world = env_to_basin.world

    assert gym.memory.snapshot() == memory_after_stream_probe
    assert _water_region(world) == "basin"
    assert all(
        item["action"] != "probe"
        for item in generate_valid_actions(world, "nova")
    )

    environmental_transitions = tuple(
        (
            event["tick_id"],
            tuple(
                (item["from_region"], item["to_region"], item["generation"])
                for item in event.get("transitions", ())
            ),
        )
        for event in sorted(world["events"].values(), key=lambda item: item["tick_id"])
        if event.get("type") == "environmental_tick"
    )

    return (
        tuple((item.mode, item.proposal["action"]) for item in discovery),
        spring_key,
        probe_diag["context_key"],
        stream_prior.active,
        stream_prediction.ambiguous,
        stream_prediction.reason,
        old_region_decision.mode,
        old_region_decision.proposal["action"],
        stream_decision.mode,
        stream_decision.proposal["action"],
        stream_step.current_regime.active,
        stream_step.current_regime.pending is not None,
        _water_region(world),
        _trace_regions(world),
        len(gym.memory.snapshot()),
        environmental_transitions,
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_003_water_moves_without_nov_action_and_memory_stays_read_only():
    world, _needs, gym, _discovery, _steps = _establish_spring_experience()
    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes
    action_events_before = tuple(
        sorted(
            event_id
            for event_id, event in world["events"].items()
            if event.get("type") == "action_committed"
        )
    )

    ticks = advance_environmental_agents(world, ticks=2)
    moved = ticks[-1].world

    assert ticks[0].transitions == ()
    assert len(ticks[1].transitions) == 1
    assert ticks[1].transitions[0]["from_region"] == "spring"
    assert ticks[1].transitions[0]["to_region"] == "stream"
    assert _water_region(moved) == "stream"
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before

    action_events_after = tuple(
        sorted(
            event_id
            for event_id, event in moved["events"].items()
            if event.get("type") == "action_committed"
        )
    )
    assert action_events_after == action_events_before


def test_life_gate_003_water_presence_controls_world_action_availability():
    world, needs, gym, _discovery, _steps = _establish_spring_experience()
    world = advance_environmental_agents(world, ticks=2)[-1].world

    at_spring = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" not in at_spring

    decision_at_spring = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert decision_at_spring.mode == "need"
    assert "live:entity:water_01" not in decision_at_spring.request.state.state_addresses

    world = relocate_entity(world, "nova", "stream")
    at_stream = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in at_stream

    decision_at_stream = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert decision_at_stream.mode == "curiosity"
    assert decision_at_stream.proposal["action"] == "probe"
    assert "live:entity:water_01" in decision_at_stream.request.state.state_addresses


def test_life_gate_003_situated_regime_does_not_leak_but_structural_ambiguity_transfers():
    signature = _run_gate_signature()
    (
        discovery,
        spring_key,
        stream_key,
        stream_active,
        stream_ambiguous,
        stream_reason,
        _old_mode,
        _old_action,
        stream_mode,
        stream_action,
        stream_current_active,
        stream_pending,
        _water_region_final,
        _trace_regions_final,
        memory_count,
        _transitions,
        _tick,
        _version,
    ) = signature

    assert discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert spring_key != stream_key
    assert stream_active is None

    # Structural topology transfers, but literal-free geometry cannot distinguish the
    # two novel candidate consequence addresses. The new situated context therefore
    # remains ambiguous and curiosity legitimately probes again.
    assert stream_ambiguous is True
    assert stream_reason == "multiple-compatible-world-candidates"
    assert stream_mode == "curiosity"
    assert stream_action == "probe"

    # One observation in the new situated context is not enough to establish a regime.
    assert stream_current_active is None
    assert stream_pending is True
    assert memory_count == 3


def test_life_gate_003_water_leaves_persistent_history_across_regions():
    signature = _run_gate_signature()
    water_region = signature[12]
    trace_regions = signature[13]
    transitions = signature[15]

    assert water_region == "basin"
    assert trace_regions == ("spring", "stream")

    nonempty = tuple(item for item in transitions if item[1])
    assert len(nonempty) == 2
    assert nonempty[0][1] == (("spring", "stream", 1),)
    assert nonempty[1][1] == (("stream", "basin", 2),)


def test_life_gate_003_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
