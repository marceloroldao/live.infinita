from __future__ import annotations

from copy import deepcopy

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
from reality_slice import Modality, TemporalAssociator

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from reality_slice_bridge import (
    reality_window_from_world_rule,
    sensor_pattern_id,
)
from scenario_life_gate_008 import build_life_gate_008_world


def _trajectory(*, episode_id: int, time_origin: float = 0.0):
    world = build_life_gate_008_world(episode_id=episode_id)

    frame0 = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = frame0.world

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    frame1 = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = frame1.world

    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    frame2 = sample_multimodal_sensor_frame(world, observer_id="nova")
    world = frame2.world

    before_bridge = deepcopy(world)
    window = reality_window_from_world_rule(
        world,
        observer_id="nova",
        time_origin=time_origin,
    )
    assert world == before_bridge
    return world, window, (frame0, frame1, frame2)


def _key(a: int, b: int):
    return (a, b) if a < b else (b, a)


def _direction_probability_for_temporal_order(link, first_pattern: int, second_pattern: int):
    forward, simultaneous, backward = link.direction_probabilities()
    if first_pattern < second_pattern:
        return forward, simultaneous, backward
    return backward, simultaneous, forward


def test_life_gate_008_three_sensor_frames_become_one_temporal_reality_slice():
    _world, window, frames = _trajectory(episode_id=1)

    assert window.frame_ids == tuple(frame.frame_id for frame in frames)
    assert len(window.frame_ticks) == 3
    assert window.frame_ticks[1] - window.frame_ticks[0] == 2
    assert window.frame_ticks[2] - window.frame_ticks[1] == 2

    rs = window.reality_slice
    assert len(rs.occurrences) == 12
    assert {item.modality for item in rs.occurrences} == {Modality.SENSOR}
    assert len(rs.provenance) == 3

    starts = sorted({round(item.t_start, 8) for item in rs.occurrences})
    assert starts == [0.0, 0.2, 0.4]

    # Four independent sensor channels coexist in every synchronized frame.
    assert [round(item.t_start, 8) for item in rs.occurrences].count(0.0) == 4
    assert [round(item.t_start, 8) for item in rs.occurrences].count(0.2) == 4
    assert [round(item.t_start, 8) for item in rs.occurrences].count(0.4) == 4


def test_life_gate_008_pattern_identity_is_stable_but_slice_identity_is_independent():
    _world_a, a, _frames_a = _trajectory(episode_id=10)
    _world_b, b, _frames_b = _trajectory(episode_id=11)

    assert a.reality_slice.slice_id != b.reality_slice.slice_id

    patterns_a = {(item.sensor_id, item.band_id): item.pattern_id for item in a.patterns}
    patterns_b = {(item.sensor_id, item.band_id): item.pattern_id for item in b.patterns}
    assert patterns_a == patterns_b

    assert patterns_a[("s_intensity", "i2")] == sensor_pattern_id("s_intensity", "i2")
    assert patterns_a[("s_intensity", "i1")] == sensor_pattern_id("s_intensity", "i1")
    assert patterns_a[("s_intensity", "i0")] == sensor_pattern_id("s_intensity", "i0")


def test_life_gate_008_temporal_distance_changes_association_strength():
    engine = TemporalAssociator(
        lambda0=0.0,
        simultaneous_delta=0.01,
        default_tau=0.5,
    )

    windows = []
    for episode_id in range(20, 28):
        _world, window, _frames = _trajectory(episode_id=episode_id)
        windows.append(window)
        engine.ingest(window.reality_slice)

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    i0 = sensor_pattern_id("s_intensity", "i0")

    near = engine.links[_key(i2, i1)]
    far = engine.links[_key(i2, i0)]

    assert near.repetitions == 8
    assert far.repetitions == 8
    assert near.rho > far.rho

    expected, simultaneous, opposite = _direction_probability_for_temporal_order(
        near,
        i2,
        i1,
    )
    assert expected > 0.99
    assert simultaneous < 0.01
    assert opposite < 0.01
    assert abs(abs(near.mean_dt) - 0.2) < 1e-9


def test_life_gate_008_independent_repetition_reinforces_same_transition():
    engine = TemporalAssociator(lambda0=0.0, default_tau=0.5)

    _world1, first, _frames1 = _trajectory(episode_id=30)
    engine.ingest(first.reality_slice)

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    link = engine.links[_key(i2, i1)]
    rho_after_one = link.rho
    assert link.repetitions == 1

    _world2, second, _frames2 = _trajectory(episode_id=31)
    engine.ingest(second.reality_slice)

    link = engine.links[_key(i2, i1)]
    assert link.repetitions == 2
    assert link.rho > rho_after_one


def test_life_gate_008_consolidated_recurrence_resists_forgetting():
    weak = TemporalAssociator(lambda0=0.1, default_tau=0.5)
    strong = TemporalAssociator(lambda0=0.1, default_tau=0.5)

    _world, weak_window, _frames = _trajectory(episode_id=40, time_origin=0.0)
    weak.ingest(weak_window.reality_slice)

    for episode_id in range(50, 60):
        _world, window, _frames = _trajectory(
            episode_id=episode_id,
            time_origin=0.0,
        )
        strong.ingest(window.reality_slice)

    i2 = sensor_pattern_id("s_intensity", "i2")
    i1 = sensor_pattern_id("s_intensity", "i1")
    key = _key(i2, i1)

    weak._forget(weak.links[key], 100.0)
    strong._forget(strong.links[key], 100.0)

    assert strong.links[key].repetitions == 10
    assert weak.links[key].repetitions == 1
    assert strong.links[key].rho > weak.links[key].rho


def test_life_gate_008_presemantic_temporal_learning_does_not_write_world_or_memoria():
    world = build_life_gate_008_world(episode_id=70)
    gym = SituatedLiveCognitiveGymV2(
        min_independent_episodes=2,
        min_contiguous_support=2,
    )
    memory_before = gym.memory.snapshot()
    regimes_before = gym.regimes

    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    world = sample_multimodal_sensor_frame(world, observer_id="nova").world

    before_bridge = deepcopy(world)
    window = reality_window_from_world_rule(world, observer_id="nova")
    engine = TemporalAssociator(lambda0=0.0)
    engine.ingest(window.reality_slice)

    assert world == before_bridge
    assert gym.memory.snapshot() == memory_before
    assert gym.regimes == regimes_before
    assert engine.links


def test_life_gate_008_is_deterministic():
    _world_a, a, _frames_a = _trajectory(episode_id=80)
    _world_b, b, _frames_b = _trajectory(episode_id=80)

    assert a == b

    engine_a = TemporalAssociator(lambda0=0.0)
    engine_b = TemporalAssociator(lambda0=0.0)
    engine_a.ingest(a.reality_slice)
    engine_b.ingest(b.reality_slice)

    signature_a = tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                link.mean_dt,
                link.direction_probabilities(),
            )
            for key, link in engine_a.links.items()
        )
    )
    signature_b = tuple(
        sorted(
            (
                key,
                link.rho,
                link.repetitions,
                link.mean_dt,
                link.direction_probabilities(),
            )
            for key, link in engine_b.links.items()
        )
    )
    assert signature_a == signature_b
