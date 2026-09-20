from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import execute_validated_action
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
from scenario_life_gate_007 import build_life_gate_007_world, initial_nov_needs_007


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


def _bands(world):
    readings = (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
    )
    return tuple(
        sorted((sensor_id, reading["band_id"]) for sensor_id, reading in readings.items())
    )


def _learn_current_context_twice(gym, world, needs):
    decisions = []
    steps = []
    for _ in range(2):
        decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
        assert decision.mode == "curiosity"
        assert decision.proposal["action"] == "probe"
        world, needs, step = _commit_and_learn(gym, world, needs, decision)
        decisions.append(decision)
        steps.append(step)
    assert steps[-1].current_regime.active is not None
    return world, needs, tuple(decisions), tuple(steps)


def _run_gate_signature():
    world = build_life_gate_007_world()
    initial_frame = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = initial_frame.world
    assert _bands(world) == (
        ("s_flow", "d0"),
        ("s_intensity", "i2"),
        ("s_presence", "p1"),
        ("s_trend", "t0"),
    )

    needs = initial_nov_needs_007(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    world, needs, initial_decisions, initial_steps = _learn_current_context_twice(
        gym, world, needs
    )
    initial_key = initial_steps[-1].context_key

    memory_before_physics = gym.memory.snapshot()
    regimes_before_physics = gym.regimes

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    frame_1 = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = frame_1.world

    assert gym.memory.snapshot() == memory_before_physics
    assert gym.regimes == regimes_before_physics
    assert _bands(world) == (
        ("s_flow", "d1"),
        ("s_intensity", "i1"),
        ("s_presence", "p1"),
        ("s_trend", "t2"),
    )

    decision_1 = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert decision_1.mode == "curiosity"
    diag_1 = next(
        value for value in decision_1.diagnostics.values()
        if value["action"] == "probe"
    )
    assert diag_1["context_key"] != initial_key
    assert diag_1["prior_regime"].active is None
    assert diag_1["effective_prediction"].ambiguous is True

    world, needs, frame1_decisions, frame1_steps = _learn_current_context_twice(
        gym, world, needs
    )
    frame1_key = frame1_steps[-1].context_key
    assert frame1_key == diag_1["context_key"]
    assert frame1_key != initial_key

    memory_before_second_physics = gym.memory.snapshot()
    regimes_before_second_physics = gym.regimes

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    frame_2 = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = frame_2.world

    assert gym.memory.snapshot() == memory_before_second_physics
    assert gym.regimes == regimes_before_second_physics
    assert _bands(world) == (
        ("s_flow", "d0"),
        ("s_intensity", "i0"),
        ("s_presence", "p1"),
        ("s_trend", "t2"),
    )

    decision_2 = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert decision_2.mode == "curiosity"
    diag_2 = next(
        value for value in decision_2.diagnostics.values()
        if value["action"] == "probe"
    )

    assert diag_2["context_key"] not in (initial_key, frame1_key)
    assert diag_2["prior_regime"].active is None
    assert diag_2["effective_prediction"].ambiguous is True

    serialized = "|".join(decision_2.request.state.state_addresses)
    for forbidden in (
        "raw_value",
        "source_value",
        "environmental_distribution",
        "multimodal_context",
        "water_falling",
        "water_flowing",
    ):
        assert forbidden not in serialized

    return (
        initial_frame.frame_id,
        frame_1.frame_id,
        frame_2.frame_id,
        initial_key,
        frame1_key,
        diag_2["context_key"],
        _bands(world),
        diag_1["effective_prediction"].reason,
        diag_2["effective_prediction"].reason,
        tuple((item.mode, item.proposal["action"]) for item in initial_decisions),
        tuple((item.mode, item.proposal["action"]) for item in frame1_decisions),
        len(gym.memory.snapshot()),
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_007_multichannel_frame_changes_context_without_composite_semantics():
    signature = _run_gate_signature()
    (
        frame0_id,
        frame1_id,
        frame2_id,
        key0,
        key1,
        key2,
        final_bands,
        reason1,
        reason2,
        initial_discovery,
        frame1_discovery,
        memory_count,
        _tick,
        _version,
    ) = signature

    assert len({frame0_id, frame1_id, frame2_id}) == 3
    assert len({key0, key1, key2}) == 3
    assert initial_discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert frame1_discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert reason1 == "multiple-compatible-world-candidates"
    assert reason2 == "multiple-compatible-world-candidates"
    assert final_bands == (
        ("s_flow", "d0"),
        ("s_intensity", "i0"),
        ("s_presence", "p1"),
        ("s_trend", "t2"),
    )
    assert memory_count == 4


def test_life_gate_007_sensor_sampling_and_physics_do_not_write_memoria():
    world = build_life_gate_007_world()
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    needs = initial_nov_needs_007(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )
    world, needs, _decisions, _steps = _learn_current_context_twice(gym, world, needs)

    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before


def test_life_gate_007_channels_remain_independent_in_cognitive_projection():
    world = build_life_gate_007_world()
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    needs = initial_nov_needs_007(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    state = decision.request.state.state_addresses

    sensor_relations = tuple(
        address for address in state if address.startswith("live:relation:rel_sensor_")
    )
    sensor_entities = tuple(
        address for address in state if address.startswith("live:entity:sensor_reading_")
    )

    assert len(sensor_relations) == 4
    assert len(sensor_entities) == 4
    serialized = "|".join(state)
    assert "multimodal_context" not in serialized


def test_life_gate_007_hidden_values_do_not_enter_memoria():
    world = build_life_gate_007_world()
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    needs = initial_nov_needs_007(world)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    serialized = "|".join(decision.request.state.state_addresses)

    for forbidden in (
        "raw_value",
        "source_value",
        "by_region",
        "initial_total",
        "evaporated_total",
        "environmental_distribution",
    ):
        assert forbidden not in serialized


def test_life_gate_007_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
