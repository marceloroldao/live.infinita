from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame


@dataclass(frozen=True, slots=True)
class EnvironmentalSensorFutureCandidate:
    candidate_id: str
    observer_id: str
    sensor_id: str
    band_id: str
    target_id: str
    region_id: str
    source_tick: int
    source_version: int
    physical_tick: int
    sensor_tick: int
    physical_event_id: str
    sensor_frame_id: str


@dataclass(frozen=True, slots=True)
class EnvironmentalSensorFutureSet:
    observer_id: str
    source_tick: int
    source_version: int
    candidates: tuple[EnvironmentalSensorFutureCandidate, ...]


def _preview_rule(world: dict[str, Any]) -> dict[str, Any]:
    rule = (world.get("rules") or {}).get("environmental_future_preview") or {}
    runtime = str(rule.get("runtime") or "")
    lookahead_ticks = int(rule.get("lookahead_ticks", 0))
    if runtime != "distributed_environmental":
        raise ValueError("environmental future preview runtime must be distributed_environmental")
    if lookahead_ticks != 1:
        raise ValueError("Life Gate 012 supports exactly one physical lookahead tick")
    return rule


def enumerate_next_distributed_sensor_candidates(
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_ids: Iterable[str] | None = None,
) -> EnvironmentalSensorFutureSet:
    """Preview the next physical distributed tick and resulting sensor frame.

    The source world is never mutated. Candidate bands are obtained by running the
    actual distributed-environment physics and actual multimodal sensor sampler on
    internal copies. No candidate band is supplied by Memoria.ia or by the caller.
    """
    _preview_rule(world)
    source_tick = int(world.get("current_tick", 0))
    source_version = int(world.get("current_version", 0))

    physical = advance_distributed_environmental_agents(world, ticks=1)[0]
    sensed = sample_multimodal_sensor_frame(
        physical.world,
        observer_id=observer_id,
    )

    requested = None
    if sensor_ids is not None:
        requested = {str(value) for value in sensor_ids}
        if not requested or "" in requested:
            raise ValueError("sensor_ids must contain non-empty values")

    candidates: list[EnvironmentalSensorFutureCandidate] = []
    for sample in sorted(sensed.samples, key=lambda item: item.sensor_id):
        if requested is not None and sample.sensor_id not in requested:
            continue
        seed = "|".join(
            (
                str(world.get("world_id") or ""),
                observer_id,
                sample.sensor_id,
                sample.band_id,
                str(source_version),
                str(source_tick),
                physical.event["event_id"],
                sensed.frame_id,
            )
        )
        candidate_id = "physical_future_" + sha256(seed.encode("utf-8")).hexdigest()[:24]
        candidates.append(
            EnvironmentalSensorFutureCandidate(
                candidate_id=candidate_id,
                observer_id=observer_id,
                sensor_id=sample.sensor_id,
                band_id=sample.band_id,
                target_id=sample.target_id,
                region_id=sample.region_id,
                source_tick=source_tick,
                source_version=source_version,
                physical_tick=int(physical.event["tick_id"]),
                sensor_tick=int(sensed.event["tick_id"]),
                physical_event_id=str(physical.event["event_id"]),
                sensor_frame_id=sensed.frame_id,
            )
        )

    if requested is not None:
        found = {item.sensor_id for item in candidates}
        missing = tuple(sorted(requested - found))
        if missing:
            raise ValueError(f"requested sensors not present in preview: {missing}")

    return EnvironmentalSensorFutureSet(
        observer_id=observer_id,
        source_tick=source_tick,
        source_version=source_version,
        candidates=tuple(candidates),
    )
