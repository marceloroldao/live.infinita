from __future__ import annotations

from copy import deepcopy

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from reality_slice import TemporalAssociator

from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from memoria_v2_adapter import observer_state_addresses
from multiagent_environment_runtime import (
    advance_coupled_environmental_step,
)
from multiagent_temporal_prediction_runtime import (
    predict_multiagent_environmental_sensor,
)
from reality_slice_bridge import reality_window_from_world_rule
from scenario_life_gate_014 import build_life_gate_014_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


def _episode(episode_id: int, wind_phase_id: str):
    world = build_life_gate_014_world(
        episode_id=episode_id,
        wind_phase_id=wind_phase_id,
    )
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    first = advance_coupled_environmental_step(
        world,
        observer_id="nova",
    )
    second = advance_coupled_environmental_step(
        first.world,
        observer_id="nova",
    )

    window = reality_window_from_world_rule(
        second.world,
        observer_id="nova",
    )
    return second.world, window


def _memory_from_phases(gust_ids=(), lull_ids=()):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in gust_ids:
        world, window = _episode(episode_id, "w_gust_a")
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    for episode_id in lull_ids:
        world, window = _episode(episode_id, "w_lull_a")
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    memory = StructuralTemporalObservationMemory()
    if last_world is None:
        return memory, engine

    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    for candidate in admitted_candidates(decisions):
        ingest_temporal_evidence_candidate(memory, candidate)
    return memory, engine


def _fresh_world(episode_id: int, phase_id: str):
    world = build_life_gate_014_world(
        episode_id=episode_id,
        wind_phase_id=phase_id,
    )
    return sample_multimodal_sensor_frame(
        world,
        observer_id="nova",
    ).world


def _flow_band(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_flow"]["band_id"]
    )


def test_life_gate_014_same_nov_observable_state_can_have_different_futures_from_wind_state():
    gust = _fresh_world(701, "w_gust_a")
    lull = _fresh_world(702, "w_lull_a")

    assert _flow_band(gust) == _flow_band(lull) == "d0"
    assert observer_state_addresses(gust, "nova") == observer_state_addresses(
        lull,
        "nova",
    )

    empty = StructuralTemporalObservationMemory()
    gust_prediction = predict_multiagent_environmental_sensor(
        empty,
        gust,
        observer_id="nova",
        sensor_id="s_flow",
    )
    lull_prediction = predict_multiagent_environmental_sensor(
        empty,
        lull,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert gust_prediction.physical_futures.candidates[0].band_id == "d1"
    assert lull_prediction.physical_futures.candidates[0].band_id == "d2"
    assert (
        gust_prediction.physical_futures.candidates[0].influence_action_id
        == "wind_open_channel"
    )
    assert (
        lull_prediction.physical_futures.candidates[0].influence_action_id
        == "wind_close_channel"
    )


def test_life_gate_014_memory_of_both_histories_recognizes_world_resolved_future_not_ambiguous_branch():
    memory, _engine = _memory_from_phases(
        gust_ids=(711, 712, 713, 714, 715),
        lull_ids=(716, 717, 718, 719, 720),
    )

    gust = _fresh_world(721, "w_gust_a")
    lull = _fresh_world(722, "w_lull_a")

    gust_prediction = predict_multiagent_environmental_sensor(
        memory,
        gust,
        observer_id="nova",
        sensor_id="s_flow",
    )
    lull_prediction = predict_multiagent_environmental_sensor(
        memory,
        lull,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert len(gust_prediction.physical_futures.candidates) == 1
    assert len(lull_prediction.physical_futures.candidates) == 1

    assert gust_prediction.physical_futures.candidates[0].band_id == "d1"
    assert gust_prediction.resolution.resolved is True
    assert gust_prediction.resolution.ambiguous is False

    assert lull_prediction.physical_futures.candidates[0].band_id == "d2"
    assert lull_prediction.resolution.resolved is True
    assert lull_prediction.resolution.ambiguous is False


def test_life_gate_014_open_only_memory_cannot_override_lull_agent_causality():
    memory, _engine = _memory_from_phases(
        gust_ids=(731, 732, 733, 734, 735),
    )
    world = _fresh_world(740, "w_lull_a")
    before = deepcopy(world)

    prediction = predict_multiagent_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert prediction.physical_futures.candidates[0].band_id == "d2"
    assert prediction.resolution.resolved is False
    assert prediction.resolution.ambiguous is False
    assert prediction.resolution.reason == "no-supported-world-continuation"
    assert world == before

    committed = advance_coupled_environmental_step(
        world,
        observer_id="nova",
    )
    assert _flow_band(committed.world) == "d2"
    assert committed.influence.event["actor"] == "wind_01"
    assert committed.influence.influences[0]["action_id"] == "wind_close_channel"


def test_life_gate_014_wind_action_is_authoritative_event_before_water_consequence():
    memory, _engine = _memory_from_phases(
        gust_ids=(741, 742, 743, 744, 745),
        lull_ids=(746, 747, 748, 749, 750),
    )
    world = _fresh_world(751, "w_gust_a")

    prediction = predict_multiagent_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )
    candidate = prediction.physical_futures.candidates[0]

    assert candidate.influence_agent_id == "wind_01"
    assert candidate.influence_phase_id == "w_gust_a"
    assert candidate.influence_action_id == "wind_open_channel"
    assert candidate.influence_next_phase_id == "w_gust_b"
    assert candidate.influence_tick + 1 == candidate.physical_tick
    assert candidate.physical_tick + 1 == candidate.sensor_tick

    committed = advance_coupled_environmental_step(
        world,
        observer_id="nova",
    )
    assert committed.influence.event["tick_id"] < committed.distributed.event["tick_id"]
    assert committed.distributed.event["tick_id"] < committed.sensor.event["tick_id"]


def test_life_gate_014_memoria_resolution_does_not_receive_wind_semantics_or_hidden_water_values():
    memory, _engine = _memory_from_phases(
        gust_ids=(761, 762, 763, 764, 765),
        lull_ids=(766, 767, 768, 769, 770),
    )
    world = _fresh_world(771, "w_gust_a")

    prediction = predict_multiagent_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    serialized = repr(prediction.resolution).lower()
    for forbidden in (
        "wind",
        "gust",
        "lull",
        "open_channel",
        "close_channel",
        "by_region",
        "initial_total",
        "evaporated_total",
        "environmental_distribution",
        "raw_value",
        "source_value",
    ):
        assert forbidden not in serialized


def test_life_gate_014_prediction_is_read_only_over_world_and_memory():
    memory, _engine = _memory_from_phases(
        gust_ids=(781, 782, 783, 784, 785),
        lull_ids=(786, 787, 788, 789, 790),
    )
    world = _fresh_world(791, "w_lull_a")
    world_before = deepcopy(world)
    memory_before = memory.snapshot()

    _ = predict_multiagent_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert world == world_before
    assert memory.snapshot() == memory_before


def test_life_gate_014_is_deterministic():
    memory_a, _engine_a = _memory_from_phases(
        gust_ids=(801, 802, 803, 804, 805),
        lull_ids=(806, 807, 808, 809, 810),
    )
    memory_b, _engine_b = _memory_from_phases(
        gust_ids=(801, 802, 803, 804, 805),
        lull_ids=(806, 807, 808, 809, 810),
    )
    world_a = _fresh_world(811, "w_gust_a")
    world_b = _fresh_world(811, "w_gust_a")

    a = predict_multiagent_environmental_sensor(
        memory_a,
        world_a,
        observer_id="nova",
        sensor_id="s_flow",
    )
    b = predict_multiagent_environmental_sensor(
        memory_b,
        world_b,
        observer_id="nova",
        sensor_id="s_flow",
    )

    assert a == b
