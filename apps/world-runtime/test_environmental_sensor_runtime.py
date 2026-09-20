from copy import deepcopy

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_perception import project_environmental_presence
from environmental_sensor_runtime import (
    project_environmental_sensor_readings,
    sample_environmental_sensors,
)
from memoria_v2_adapter import observer_state_addresses
from scenario_life_gate_006 import build_life_gate_006_world


def _sensor_reading(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]["water_local_level"]
    )


def test_sensor_initial_sample_reports_only_coarse_band():
    world = build_life_gate_006_world()
    tick = sample_environmental_sensors(world, observer_id="nova")

    sample = tick.samples[0]
    assert sample.raw_value == 100
    assert sample.committed_band_id == "q2"

    projected = project_environmental_presence(tick.world, "nova")
    projected = project_environmental_sensor_readings(projected, "nova")
    state = observer_state_addresses(projected, "nova")
    serialized = "|".join(state)

    assert "live:entity:water_01" in state
    assert "raw_value" not in serialized
    assert "noisy_value" not in serialized
    assert "100" not in serialized


def test_sensor_noise_is_deterministic_for_same_world_snapshot():
    world = build_life_gate_006_world()

    a = sample_environmental_sensors(world, observer_id="nova")
    b = sample_environmental_sensors(world, observer_id="nova")

    assert a.samples == b.samples
    assert a.event == b.event
    assert a.delta == b.delta


def test_sensor_persistence_requires_repeated_lower_band_before_switch():
    world = build_life_gate_006_world()
    world = sample_environmental_sensors(world, observer_id="nova").world
    assert _sensor_reading(world)["band_id"] == "q2"

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    assert (
        world["entities"]["water_01"]["components"]["environmental_distribution"]["by_region"]["spring"]
        == 20
    )

    first = sample_environmental_sensors(world, observer_id="nova")
    first_reading = _sensor_reading(first.world)
    assert first.samples[0].candidate_band_id == "q1"
    assert first_reading["band_id"] == "q2"
    assert first_reading["pending_band_id"] == "q1"
    assert first_reading["pending_count"] == 1

    second = sample_environmental_sensors(first.world, observer_id="nova")
    second_reading = _sensor_reading(second.world)
    assert second.samples[0].candidate_band_id == "q1"
    assert second_reading["band_id"] == "q1"
    assert second_reading["pending_band_id"] is None
    assert second_reading["pending_count"] == 0


def test_sensor_hysteresis_rejects_boundary_chatter():
    world = build_life_gate_006_world()
    rule = world["rules"]["environmental_sensors"][0]
    rule["noise_amplitude"] = 0

    # Start safely in q2.
    world["entities"]["water_01"]["components"]["environmental_distribution"]["by_region"]["spring"] = 40
    world["entities"]["water_01"]["components"]["environmental_distribution"]["initial_total"] = 40
    world = sample_environmental_sensors(world, observer_id="nova").world
    assert _sensor_reading(world)["band_id"] == "q2"

    # 34 is below q2's nominal threshold 35, but within 3 units of hysteresis.
    distribution = world["entities"]["water_01"]["components"]["environmental_distribution"]
    distribution["by_region"]["spring"] = 34
    distribution["initial_total"] = 34
    sampled = sample_environmental_sensors(world, observer_id="nova")

    assert sampled.samples[0].candidate_band_id == "q2"
    assert _sensor_reading(sampled.world)["band_id"] == "q2"
    assert _sensor_reading(sampled.world)["pending_band_id"] is None


def test_two_hidden_quantities_in_same_band_have_same_cognitive_projection():
    base = build_life_gate_006_world()
    base["rules"]["environmental_sensors"][0]["noise_amplitude"] = 0

    a = deepcopy(base)
    da = a["entities"]["water_01"]["components"]["environmental_distribution"]
    da["by_region"]["spring"] = 40
    da["initial_total"] = 40
    a = sample_environmental_sensors(a, observer_id="nova").world

    b = deepcopy(base)
    db = b["entities"]["water_01"]["components"]["environmental_distribution"]
    db["by_region"]["spring"] = 80
    db["initial_total"] = 80
    b = sample_environmental_sensors(b, observer_id="nova").world

    pa = project_environmental_sensor_readings(project_environmental_presence(a, "nova"), "nova")
    pb = project_environmental_sensor_readings(project_environmental_presence(b, "nova"), "nova")

    assert _sensor_reading(a)["band_id"] == _sensor_reading(b)["band_id"] == "q2"
    assert observer_state_addresses(pa, "nova") == observer_state_addresses(pb, "nova")


def test_sensor_projection_is_read_only():
    world = build_life_gate_006_world()
    world = sample_environmental_sensors(world, observer_id="nova").world
    before = deepcopy(world)

    projected = project_environmental_sensor_readings(world, "nova")

    assert world == before
    assert projected != world
