from __future__ import annotations

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import execute_validated_action, generate_valid_actions
from environmental_agent_runtime import advance_reactive_environmental_agents
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
from scenario_life_gate_004 import build_life_gate_004_world, initial_nov_needs_004
from spatial_runtime import relocate_entity
from world_property_runtime import update_environmental_route_properties


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


def _establish_spring_experience():
    world = build_life_gate_004_world()
    needs = initial_nov_needs_004(world)
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
        world, needs, step = _commit_and_learn(gym, world, needs, decision)
        decisions.append(decision)
        steps.append(step)

    assert steps[-1].current_regime.active is not None
    assert _water_region(world) == "spring"
    return world, needs, gym, tuple(decisions), tuple(steps)


def _reroute_spring_to_hollow(world):
    world = update_environmental_route_properties(
        world,
        region_id="spring",
        route_id="spring_channel",
        properties={
            "capacity": 2,
            "descent": 6,
            "retention": 2,
            "evaporation": 3,
        },
    )
    world = update_environmental_route_properties(
        world,
        region_id="spring",
        route_id="spring_hollow",
        properties={
            "capacity": 9,
            "descent": 4,
            "retention": 7,
            "evaporation": 1,
        },
    )
    return world


def _run_gate_signature():
    world, needs, gym, discovery, spring_steps = _establish_spring_experience()
    spring_key = spring_steps[-1].context_key

    memory_before_properties = gym.memory.snapshot()
    regimes_before_properties = gym.regimes

    world = _reroute_spring_to_hollow(world)
    assert gym.memory.snapshot() == memory_before_properties
    assert gym.regimes == regimes_before_properties

    reactive = advance_reactive_environmental_agents(world, ticks=1)[0]
    world = reactive.world

    assert len(reactive.transitions) == 1
    transition = reactive.transitions[0]
    assert transition["route_id"] == "spring_hollow"
    assert transition["to_region"] == "hollow"
    assert _water_region(world) == "hollow"
    assert gym.memory.snapshot() == memory_before_properties
    assert gym.regimes == regimes_before_properties

    spring_actions = generate_valid_actions(world, "nova")
    assert all(item["action"] != "probe" for item in spring_actions)
    spring_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert spring_decision.mode == "need"
    assert "live:entity:water_01" not in spring_decision.request.state.state_addresses

    world = relocate_entity(world, "nova", "hollow")

    hollow_decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert hollow_decision.mode == "curiosity"
    assert hollow_decision.proposal["action"] == "probe"
    assert hollow_decision.proposal["target"] == "water_01"
    assert "live:entity:water_01" in hollow_decision.request.state.state_addresses

    hidden_names = ("capacity", "descent", "retention", "evaporation")
    for address in hollow_decision.request.state.state_addresses:
        assert all(name not in address for name in hidden_names)

    probe_diag = next(
        value
        for value in hollow_decision.diagnostics.values()
        if value["action"] == "probe"
    )
    hollow_prior = probe_diag["prior_regime"]
    hollow_prediction = probe_diag["effective_prediction"]

    world, needs, hollow_step = _commit_and_learn(
        gym,
        world,
        needs,
        hollow_decision,
    )

    trace = world["entities"][transition["trace_id"]]

    return (
        tuple((item.mode, item.proposal["action"]) for item in discovery),
        spring_key,
        probe_diag["context_key"],
        hollow_prior.active,
        hollow_prediction.ambiguous,
        hollow_prediction.reason,
        spring_decision.mode,
        spring_decision.proposal["action"],
        hollow_decision.mode,
        hollow_decision.proposal["action"],
        hollow_step.current_regime.active,
        hollow_step.current_regime.pending is not None,
        transition["route_id"],
        transition["to_region"],
        tuple(sorted(transition["route_properties"].items())),
        tuple(sorted(trace["components"]["route_properties"].items())),
        len(gym.memory.snapshot()),
        world["current_tick"],
        world["current_version"],
    )


def test_life_gate_004_world_properties_reroute_water_without_touching_memory():
    world, _needs, gym, _discovery, _steps = _establish_spring_experience()
    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes

    world = _reroute_spring_to_hollow(world)
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before

    tick = advance_reactive_environmental_agents(world, ticks=1)[0]
    assert tick.transitions[0]["route_id"] == "spring_hollow"
    assert tick.transitions[0]["to_region"] == "hollow"
    assert _water_region(tick.world) == "hollow"
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before


def test_life_gate_004_hidden_world_properties_do_not_leak_into_memoria_frame():
    world, needs, gym, _discovery, _steps = _establish_spring_experience()
    world = _reroute_spring_to_hollow(world)
    world = advance_reactive_environmental_agents(world, ticks=1)[0].world
    world = relocate_entity(world, "nova", "hollow")

    decision = choose_autonomous_action(gym=gym, world=world, needs=needs)
    assert decision.mode == "curiosity"

    serialized = "|".join(decision.request.state.state_addresses)
    for hidden in ("capacity", "descent", "retention", "evaporation"):
        assert hidden not in serialized


def test_life_gate_004_nov_reacts_to_observed_route_result_not_hidden_selector():
    signature = _run_gate_signature()
    (
        discovery,
        spring_key,
        hollow_key,
        hollow_active,
        hollow_ambiguous,
        hollow_reason,
        spring_mode,
        _spring_action,
        hollow_mode,
        hollow_action,
        hollow_current_active,
        hollow_pending,
        route_id,
        to_region,
        route_properties,
        trace_properties,
        memory_count,
        _tick,
        _version,
    ) = signature

    assert discovery == (("curiosity", "probe"), ("curiosity", "probe"))
    assert spring_key != hollow_key
    assert hollow_active is None

    assert spring_mode == "need"
    assert hollow_mode == "curiosity"
    assert hollow_action == "probe"
    assert hollow_ambiguous is True
    assert hollow_reason == "multiple-compatible-world-candidates"

    assert hollow_current_active is None
    assert hollow_pending is True
    assert memory_count == 3

    assert route_id == "spring_hollow"
    assert to_region == "hollow"
    assert dict(route_properties)["capacity"] == 9
    assert trace_properties == route_properties


def test_life_gate_004_property_change_is_part_of_world_history():
    world = build_life_gate_004_world()
    before_events = len(world["events"])
    before_deltas = len(world["deltas"])

    changed = _reroute_spring_to_hollow(world)

    property_events = [
        event
        for event in changed["events"].values()
        if event.get("type") == "environmental_route_properties_changed"
    ]
    assert len(property_events) == 2
    assert len(changed["events"]) == before_events + 2
    assert len(changed["deltas"]) == before_deltas + 2
    assert all(event["delta_id"] in changed["deltas"] for event in property_events)


def test_life_gate_004_is_deterministic():
    assert _run_gate_signature() == _run_gate_signature()
