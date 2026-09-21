from copy import deepcopy

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from environmental_state_interaction_runtime import apply_environmental_state_interactions
from scenario_life_gate_018 import build_life_gate_018_world


CASES = (
    ("w_gust_a", "b_clear", True, "d1"),
    ("w_gust_a", "b_blocked", False, "d2"),
    ("w_lull_a", "b_clear", False, "d2"),
    ("w_lull_a", "b_blocked", True, "d1"),
)


def _route_available(world):
    route = next(
        item
        for item in world["regions"]["spring"]["environmental_routes"]
        if item["route_id"] == "spring_channel"
    )
    return route.get("available", True)


def _flow_band(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_flow"]["band_id"]
    )


def test_state_interaction_truth_table_controls_real_water_physics():
    for idx, (wind_phase, barrier_phase, available, expected_band) in enumerate(CASES):
        world = build_life_gate_018_world(
            episode_id=idx + 1,
            wind_phase_id=wind_phase,
            barrier_phase_id=barrier_phase,
        )
        interacted = apply_environmental_state_interactions(world)

        assert _route_available(interacted.world) is available

        physical = advance_distributed_environmental_agents(
            interacted.world,
            ticks=1,
        )[0]
        sensed = sample_multimodal_sensor_frame(
            physical.world,
            observer_id="nova",
            sensor_ids=("s_flow",),
        )
        assert _flow_band(sensed.world) == expected_band


def test_state_interaction_is_read_only_over_source_world():
    world = build_life_gate_018_world(
        episode_id=10,
        wind_phase_id="w_gust_a",
        barrier_phase_id="b_blocked",
    )
    before = deepcopy(world)

    _ = apply_environmental_state_interactions(world)

    assert world == before


def test_state_interaction_records_exact_world_inputs_but_no_cognitive_data():
    world = build_life_gate_018_world(
        episode_id=11,
        wind_phase_id="w_lull_a",
        barrier_phase_id="b_blocked",
    )

    tick = apply_environmental_state_interactions(world)
    interaction = tick.interactions[0]

    assert interaction["case_id"] == "case_11"
    assert interaction["inputs"] == {
        "i0": "w_lull_a",
        "i1": "b_blocked",
    }
    assert tick.event["type"] == "environmental_state_interaction_applied"
    assert tick.delta["provenance"]["origin"] == (
        "environmental-state-interaction-runtime"
    )
    assert "memoria" not in repr(tick.event).lower()
    assert "temporal" not in repr(tick.event).lower()


def test_state_interaction_rejects_unknown_combination():
    world = build_life_gate_018_world(
        episode_id=12,
        wind_phase_id="w_gust_a",
        barrier_phase_id="b_clear",
    )
    world["entities"]["barrier_01"]["components"]["process_state"]["phase_id"] = (
        "b_unknown"
    )

    try:
        apply_environmental_state_interactions(world)
    except ValueError as exc:
        assert "no case" in str(exc)
    else:
        raise AssertionError("unknown state combination must be rejected")


def test_state_interaction_is_deterministic():
    world = build_life_gate_018_world(
        episode_id=13,
        wind_phase_id="w_lull_a",
        barrier_phase_id="b_clear",
    )

    a = apply_environmental_state_interactions(world)
    b = apply_environmental_state_interactions(world)

    assert a == b
