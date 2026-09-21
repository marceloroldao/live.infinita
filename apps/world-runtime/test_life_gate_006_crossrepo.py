from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import execute_validated_action
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_sensor_runtime import sample_environmental_sensors
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
from scenario_life_gate_006 import build_life_gate_006_world, initial_nov_needs_006


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


def _reading(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]["water_local_level"]
    )


def _establish_high_band_context():
    world = build_life_gate_006_world()
    world = sample_environmental_sensors(world, observer_id="nova").world
    assert _reading(world)["band_id"] == "q2"

    needs = initial_nov_needs_006(world)
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
        world, needs, step = _commit_and_learn(gym, world, needs, decision)
        decisions.append(decision)
        steps.append(step)

    assert steps[-1].current_regime.active is not None
    return world, needs, gym, tuple(decisions), tuple(steps)


def _run_gate_signature():
    world, needs, gym, discovery, high_steps = _establish_high_band_context()
    high_key = high_steps[-1].context_key

    memory_before_flow = gym.memory.snapshot()
    regimes_before_flow = gym.regimes

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    assert (
        world["entities"]["water_01"]["components"]["environmental_distribution"]["by_region"]["spring"]
        == 20
    )
    assert gym.memory.snapshot() == memory_before_flow
    assert gym.regimes == regimes_before_flow

    first_sample = sample_environmental_sensors(world, observer_id="nova")
    world = first_sample.world
    assert first_sample.samples[0].candidate_band_id == "q1"
    assert _reading(world)["band_id"] == "q2"
    assert _reading(world)["pending_band_id"] == "q1"
    assert _reading(world)["pending_count"] == 1

    after_one_sample = choose_autonomous_action(gym=gym, world=world, needs=needs)
    first_probe_diag = next(
        value
        for value in after_one_sample.diagnostics.values()
        if value["action"] == "probe"
    )

    # Persistence holds the previous sensory band, so the learned context remains valid.
    assert first_probe_diag["context_key"] == high_key
    assert first_probe_diag["effective_prediction"].resolved is True
    assert after_one_sample.mode == "need"

    memory_before_switch = gym.memory.snapshot()
    regimes_before_switch = gym.regimes

    second_sample = sample_environmental_sensors(world, observer_id="nova")
    world = second_sample.world
    assert second_sample.samples[0].candidate_band_id == "q1"
    assert _reading(world)["band_id"] == "q1"
    assert _reading(world)["pending_band_id"] is None
    assert gym.memory.snapshot() == memory_before_switch
    assert gym.regimes == regimes_before_switch

    after_switch = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert after_switch.mode == "curiosity"
    assert after_switch.proposal["action"] == "probe"

    switched_diag = next(
        value
        for value in after_switch.diagnostics.values()
        if value["action"] == "probe"
    )
    assert switched_diag["context_key"] != high_key
    assert switched_diag["prior_regime"].active is None
    assert switched_diag["effective_prediction"].ambiguous is True

    serialized = "|".join(after_switch.request.state.state_addresses)
    for hidden in (
        "raw_value",
        "noisy_value",
        "environmental_distribution",
        "initial_total",
        "evaporated_total",
        "by_region",
    ):
        assert hidden not in serialized

    world, needs, low_step = _commit_and_learn(
        gym,
        world,
        needs,
        after_switch,
    )

    assert low_step.current_regime.active is None
    assert low_step.current_regime.pending is not None

    return (
        tuple((item.mode, item.proposal["action"]) for item in discovery),
        high_key,
        first_probe_diag["context_key"],
        first_probe_diag["effective_prediction"].reason,
        after_one_sample.mode,
        switched_diag["context_key"],
        switched_diag["effective_prediction"].reason,
        after_switch.mode,
        after_switch.proposal["action"],
        _reading(world)["band_id"],
        low_step.current_regime.active,
        low_step.current_regime.pending is not None,
        len(gym.memory.snapshot()),
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_006_one_lower_sample_does_not_break_known_context():
    world, needs, gym, _discovery, steps = _establish_high_band_context()
    high_key = steps[-1].context_key

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_environmental_sensors(world, observer_id="nova").world

    assert _reading(world)["band_id"] == "q2"
    assert _reading(world)["pending_band_id"] == "q1"

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    probe_diag = next(
        value
        for value in decision.diagnostics.values()
        if value["action"] == "probe"
    )
    assert probe_diag["context_key"] == high_key
    assert probe_diag["effective_prediction"].resolved is True
    assert decision.mode == "need"


def test_life_gate_006_repeated_lower_samples_create_new_situated_context():
    signature = _run_gate_signature()
    (
        discovery,
        high_key,
        first_key,
        _first_reason,
        first_mode,
        low_key,
        low_reason,
        low_mode,
        low_action,
        committed_band,
        low_active,
        low_pending,
        memory_count,
        _tick,
        _version,
    ) = signature

    assert discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert first_key == high_key
    assert first_mode == "need"

    assert low_key != high_key
    assert low_reason == "multiple-compatible-world-candidates"
    assert low_mode == "curiosity"
    assert low_action == "probe"
    assert committed_band == "q1"

    assert low_active is None
    assert low_pending is True
    assert memory_count == 3


def test_life_gate_006_sampling_does_not_write_memoria():
    world, _needs, gym, _discovery, _steps = _establish_high_band_context()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world

    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes

    first = sample_environmental_sensors(world, observer_id="nova")
    second = sample_environmental_sensors(first.world, observer_id="nova")

    assert first.samples and second.samples
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before


def test_life_gate_006_hidden_numeric_sensor_state_does_not_leak_to_memoria():
    world, needs, gym, _discovery, _steps = _establish_high_band_context()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_environmental_sensors(world, observer_id="nova").world
    world = sample_environmental_sensors(world, observer_id="nova").world

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    serialized = "|".join(decision.request.state.state_addresses)

    for hidden in (
        "raw_value",
        "noisy_value",
        "environmental_distribution",
        "initial_total",
        "evaporated_total",
        "by_region",
    ):
        assert hidden not in serialized


def test_life_gate_006_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
