from copy import deepcopy

from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from scenario_life_gate_015 import build_life_gate_015_world


def _sample(phase_id):
    world = build_life_gate_015_world(
        episode_id=1,
        wind_phase_id=phase_id,
    )
    before = deepcopy(world)
    tick = sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
        sensor_ids=("s_agent_signal_01",),
    )
    return before, tick


def test_component_enum_sensor_collapses_persistent_wind_regimes_to_opaque_bands():
    expected = {
        "w_gust_a": "a0",
        "w_gust_b": "a0",
        "w_lull_a": "a1",
        "w_lull_b": "a1",
    }
    for phase_id, band_id in expected.items():
        _before, tick = _sample(phase_id)
        assert len(tick.samples) == 1
        sample = tick.samples[0]
        assert sample.sensor_id == "s_agent_signal_01"
        assert sample.channel_kind == "component_enum"
        assert sample.band_id == band_id


def test_component_enum_exact_phase_stays_in_world_sensor_state_not_public_event():
    _before, tick = _sample("w_gust_a")

    reading = (
        tick.world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_agent_signal_01"]
    )
    assert reading["source_value"] == "w_gust_a"
    assert reading["raw_value"] == "w_gust_a"

    serialized_event = repr(tick.event).lower()
    assert "w_gust_a" not in serialized_event
    assert "wind_open_channel" not in serialized_event
    assert tick.event["channels"] == [
        {
            "sensor_id": "s_agent_signal_01",
            "channel_kind": "component_enum",
            "band_id": "a0",
        }
    ]


def test_multisensor_filter_samples_only_requested_agent_signal():
    _before, tick = _sample("w_lull_a")

    assert tuple(sample.sensor_id for sample in tick.samples) == (
        "s_agent_signal_01",
    )
    assert tick.event["after"]["channel_count"] == 1
    assert tick.event["targets"] == ["wind_01"]


def test_component_enum_sampling_is_read_only_over_source_world():
    before, tick = _sample("w_lull_b")

    # The returned world advances because sensing is an authoritative sensor event,
    # but the source object passed to the sampler remains unchanged.
    original = build_life_gate_015_world(
        episode_id=1,
        wind_phase_id="w_lull_b",
    )
    assert before == original
    assert tick.world is not before
    assert before["current_tick"] + 1 == tick.world["current_tick"]


def test_selected_sensor_validation_rejects_unknown_channel():
    world = build_life_gate_015_world(
        episode_id=2,
        wind_phase_id="w_gust_a",
    )
    try:
        sample_multimodal_sensor_frame(
            world,
            observer_id="nova",
            sensor_ids=("missing_sensor",),
        )
    except ValueError as exc:
        assert "selected multimodal" in str(exc) or "requested sensors" in str(exc)
    else:
        raise AssertionError("unknown selected sensor must be rejected")
