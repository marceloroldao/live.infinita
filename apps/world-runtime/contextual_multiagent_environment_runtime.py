from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from distributed_environment_runtime import (
    DistributedEnvironmentalTick,
    advance_distributed_environmental_agents,
)
from environmental_context_process_runtime import (
    EnvironmentalContextProcessTick,
    advance_environmental_context_processes,
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
class ContextualMultiAgentStep:
    world: dict[str, Any]
    influence: EnvironmentalInfluenceTick
    context: EnvironmentalContextProcessTick
    distributed: DistributedEnvironmentalTick
    sensor: MultiSensorTick


def advance_contextual_multiagent_step(
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_ids: Iterable[str] | None = None,
) -> ContextualMultiAgentStep:
    """Advance Wind -> context process -> Water -> sensors.

    Each stage owns its own state transition and writes its own authoritative
    Event/Delta. The ordering is explicit and no cognitive component participates.
    """
    influence = advance_environmental_influence_agents(world, ticks=1)[0]
    context = advance_environmental_context_processes(
        influence.world,
        ticks=1,
    )[0]
    distributed = advance_distributed_environmental_agents(
        context.world,
        ticks=1,
    )[0]
    sensor = sample_multimodal_sensor_frame(
        distributed.world,
        observer_id=observer_id,
        sensor_ids=sensor_ids,
    )
    return ContextualMultiAgentStep(
        world=sensor.world,
        influence=influence,
        context=context,
        distributed=distributed,
        sensor=sensor,
    )
