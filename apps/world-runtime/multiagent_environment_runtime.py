from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from distributed_environment_runtime import (
    DistributedEnvironmentalTick,
    advance_distributed_environmental_agents,
)
from environmental_influence_agent_runtime import (
    EnvironmentalInfluenceTick,
    advance_environmental_influence_agents,
)
from environmental_multisensor_runtime import (
    MultiSensorTick,
    sample_multimodal_sensor_frame,
)


@dataclass(frozen=True, slots=True)
class CoupledEnvironmentalStep:
    world: dict[str, Any]
    influence: EnvironmentalInfluenceTick
    distributed: DistributedEnvironmentalTick
    sensor: MultiSensorTick


@dataclass(frozen=True, slots=True)
class AgentConditionedSensorFutureCandidate:
    candidate_id: str
    influence_agent_id: str
    influence_phase_id: str
    influence_action_id: str
    influence_next_phase_id: str
    observer_id: str
    sensor_id: str
    band_id: str
    target_id: str
    region_id: str
    source_tick: int
    source_version: int
    influence_tick: int
    physical_tick: int
    sensor_tick: int
    influence_event_id: str
    physical_event_id: str
    sensor_frame_id: str


@dataclass(frozen=True, slots=True)
class AgentConditionedSensorFutureSet:
    observer_id: str
    source_tick: int
    source_version: int
    influence_agent_id: str
    candidates: tuple[AgentConditionedSensorFutureCandidate, ...]


def advance_coupled_environmental_step(
    world: dict[str, Any],
    *,
    observer_id: str,
) -> CoupledEnvironmentalStep:
    """Advance influence agent -> distributed environment -> sensor frame."""
    influence = advance_environmental_influence_agents(world, ticks=1)[0]
    distributed = advance_distributed_environmental_agents(
        influence.world,
        ticks=1,
    )[0]
    sensor = sample_multimodal_sensor_frame(
        distributed.world,
        observer_id=observer_id,
    )
    return CoupledEnvironmentalStep(
        world=sensor.world,
        influence=influence,
        distributed=distributed,
        sensor=sensor,
    )


def preview_next_agent_conditioned_sensor_futures(
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_id: str,
) -> AgentConditionedSensorFutureSet:
    """Preview the next autonomous-agent-conditioned physical sensor future.

    The source world remains unchanged because every runtime stage works from copies.
    The current influence-agent phase resolves the physical route before distributed
    Water advances. No memory component participates.
    """
    if not sensor_id:
        raise ValueError("sensor_id must be non-empty")

    source_tick = int(world.get("current_tick", 0))
    source_version = int(world.get("current_version", 0))
    step = advance_coupled_environmental_step(
        world,
        observer_id=observer_id,
    )

    influences = step.influence.influences
    if len(influences) != 1:
        raise ValueError("Gate 014 requires exactly one active influence agent")
    influence = influences[0]
    agent_id = str(influence["agent_id"])

    samples = tuple(
        sample
        for sample in step.sensor.samples
        if sample.sensor_id == sensor_id
    )
    if len(samples) != 1:
        raise ValueError("requested sensor must produce exactly one sample")
    sample = samples[0]

    seed = "|".join(
        (
            str(world.get("world_id") or ""),
            agent_id,
            str(influence["phase_id"]),
            str(influence["action_id"]),
            str(influence["next_phase_id"]),
            observer_id,
            sensor_id,
            sample.band_id,
            str(source_version),
            str(source_tick),
            step.influence.event["event_id"],
            step.distributed.event["event_id"],
            step.sensor.frame_id,
        )
    )
    candidate = AgentConditionedSensorFutureCandidate(
        candidate_id=(
            "agent_conditioned_future_"
            + sha256(seed.encode("utf-8")).hexdigest()[:24]
        ),
        influence_agent_id=agent_id,
        influence_phase_id=str(influence["phase_id"]),
        influence_action_id=str(influence["action_id"]),
        influence_next_phase_id=str(influence["next_phase_id"]),
        observer_id=observer_id,
        sensor_id=sample.sensor_id,
        band_id=sample.band_id,
        target_id=sample.target_id,
        region_id=sample.region_id,
        source_tick=source_tick,
        source_version=source_version,
        influence_tick=int(step.influence.event["tick_id"]),
        physical_tick=int(step.distributed.event["tick_id"]),
        sensor_tick=int(step.sensor.event["tick_id"]),
        influence_event_id=str(step.influence.event["event_id"]),
        physical_event_id=str(step.distributed.event["event_id"]),
        sensor_frame_id=step.sensor.frame_id,
    )
    return AgentConditionedSensorFutureSet(
        observer_id=observer_id,
        source_tick=source_tick,
        source_version=source_version,
        influence_agent_id=agent_id,
        candidates=(candidate,),
    )
