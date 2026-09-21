from __future__ import annotations

from copy import deepcopy

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from reality_slice import TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from environmental_temporal_prediction_runtime import (
    predict_next_environmental_sensor,
)
from reality_slice_bridge import reality_window_from_world_rule
from scenario_life_gate_012 import build_life_gate_012_world
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


def _episode(episode_id: int):
    world = build_life_gate_012_world(episode_id=episode_id)
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    return world, reality_window_from_world_rule(world, observer_id="nova")


def _memory_from_episodes(episode_ids):
    engine = TemporalAssociator(lambda0=0.0)
    provenance = {}
    last_world = None

    for episode_id in episode_ids:
        world, window = _episode(episode_id)
        last_world = world
        engine.ingest(window.reality_slice)
        provenance[window.reality_slice.slice_id] = window.frame_ids

    decisions = select_temporal_evidence_candidates(
        engine,
        policy_from_world(last_world),
        provenance_by_slice=provenance,
    )
    memory = StructuralTemporalObservationMemory()
    for candidate in admitted_candidates(decisions):
        ingest_temporal_evidence_candidate(memory, candidate)
    return memory


def _fresh_prediction_world(episode_id: int):
    world = build_life_gate_012_world(episode_id=episode_id)
    return sample_multimodal_sensor_frame(world, observer_id="nova").world


def _intensity_band(world):
    return (
        world["entities"]["nova"]["components"]["sensor_state"]["readings"]
        ["s_intensity"]["band_id"]
    )


def test_life_gate_012_world_runtime_generates_future_before_memoria_resolves_it():
    memory = _memory_from_episodes((501, 502, 503))
    world = _fresh_prediction_world(510)

    prediction = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )

    assert prediction.current_band_id == "i2"
    assert len(prediction.physical_futures.candidates) == 1
    physical = prediction.physical_futures.candidates[0]
    assert physical.sensor_id == "s_intensity"
    assert physical.band_id == "i1"

    assert prediction.resolution.resolved is True
    assert prediction.resolution.ambiguous is False
    assert prediction.resolution.resolved_candidate is not None
    assert (
        prediction.resolution.resolved_candidate.candidate_id
        == physical.candidate_id
    )


def test_life_gate_012_previewed_future_matches_actual_committed_world_transition():
    memory = _memory_from_episodes((511, 512, 513))
    world = _fresh_prediction_world(520)

    prediction = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )
    expected_band = prediction.physical_futures.candidates[0].band_id

    committed = advance_distributed_environmental_agents(world, ticks=1)[0].world
    committed = sample_multimodal_sensor_frame(
        committed,
        observer_id="nova",
    ).world

    assert expected_band == "i1"
    assert _intensity_band(committed) == expected_band


def test_life_gate_012_memoria_with_extra_supported_future_cannot_expand_physical_set():
    # Four episodes admit both the nearer and farther temporal intensity transitions,
    # but the next one-tick physical runtime state still contains only i1.
    memory = _memory_from_episodes((521, 522, 523, 524))
    world = _fresh_prediction_world(530)

    prediction = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )

    assert len(prediction.physical_futures.candidates) == 1
    physical = prediction.physical_futures.candidates[0]
    assert physical.band_id == "i1"

    assert prediction.resolution.resolved is True
    assert prediction.resolution.resolved_candidate is not None
    assert (
        prediction.resolution.resolved_candidate.candidate_id
        == physical.candidate_id
    )
    assert len(prediction.resolution.candidates) == 1
    assert prediction.resolution.candidates[0].candidate_id == physical.candidate_id


def test_life_gate_012_empty_temporal_memory_does_not_block_or_rewrite_physics():
    memory = StructuralTemporalObservationMemory()
    world = _fresh_prediction_world(540)

    prediction = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )

    assert len(prediction.physical_futures.candidates) == 1
    assert prediction.physical_futures.candidates[0].band_id == "i1"
    assert prediction.resolution.resolved is False
    assert prediction.resolution.ambiguous is False
    assert prediction.resolution.reason == "no-supported-world-continuation"

    committed = advance_distributed_environmental_agents(world, ticks=1)[0].world
    committed = sample_multimodal_sensor_frame(
        committed,
        observer_id="nova",
    ).world
    assert _intensity_band(committed) == "i1"


def test_life_gate_012_prediction_is_read_only_over_world_and_temporal_memory():
    memory = _memory_from_episodes((541, 542, 543))
    world = _fresh_prediction_world(550)
    world_before = deepcopy(world)
    memory_before = memory.snapshot()

    _ = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )

    assert world == world_before
    assert memory.snapshot() == memory_before


def test_life_gate_012_future_metadata_originates_from_actual_preview_ticks():
    memory = _memory_from_episodes((551, 552, 553))
    world = _fresh_prediction_world(560)

    prediction = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )
    physical = prediction.physical_futures.candidates[0]

    assert physical.source_tick == world["current_tick"]
    assert physical.source_version == world["current_version"]
    assert physical.physical_tick == world["current_tick"] + 1
    assert physical.sensor_tick == world["current_tick"] + 2
    assert physical.physical_event_id.endswith("_environment_distributed")
    assert physical.sensor_frame_id.startswith("sensor_frame_")


def test_life_gate_012_is_deterministic():
    memory_a = _memory_from_episodes((561, 562, 563))
    memory_b = _memory_from_episodes((561, 562, 563))
    world_a = _fresh_prediction_world(570)
    world_b = _fresh_prediction_world(570)

    a = predict_next_environmental_sensor(
        memory_a,
        world_a,
        observer_id="nova",
        sensor_id="s_intensity",
    )
    b = predict_next_environmental_sensor(
        memory_b,
        world_b,
        observer_id="nova",
        sensor_id="s_intensity",
    )

    assert a == b


def test_life_gate_012_hidden_physical_values_do_not_enter_memoria_resolution():
    memory = _memory_from_episodes((571, 572, 573))
    world = _fresh_prediction_world(580)

    prediction = predict_next_environmental_sensor(
        memory,
        world,
        observer_id="nova",
        sensor_id="s_intensity",
    )

    physical = prediction.physical_futures.candidates[0]
    assert not hasattr(physical, "raw_value")
    assert not hasattr(physical, "source_value")

    serialized = repr(prediction.resolution).lower()
    for forbidden in (
        "raw_value",
        "source_value",
        "by_region",
        "initial_total",
        "evaporated_total",
        "environmental_distribution",
    ):
        assert forbidden not in serialized
