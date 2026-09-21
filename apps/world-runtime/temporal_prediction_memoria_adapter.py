from __future__ import annotations

from collections.abc import Iterable

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from memoria_resolutiva.structural_temporal_recall_v2 import (
    TemporalWorldCandidate,
    TemporalWorldCandidateResolution,
    resolve_temporal_world_candidates,
)

from environmental_branching_runtime import BranchingSensorFutureSet
from environmental_future_runtime import EnvironmentalSensorFutureSet
from multiagent_environment_runtime import AgentConditionedSensorFutureSet
from reality_slice_bridge import sensor_pattern_id


def temporal_sensor_pattern_address(sensor_id: str, band_id: str) -> str:
    return f"temporal:pattern:{sensor_pattern_id(sensor_id, band_id)}"


def make_temporal_world_candidates(
    candidates: Iterable[tuple[str, str, str]],
) -> tuple[TemporalWorldCandidate, ...]:
    """Normalize concrete world-offered sensor futures into opaque Memoria addresses.

    Input tuples are (candidate_id, sensor_id, band_id). This function never discovers
    or manufactures candidates; it only converts options explicitly supplied by the
    World Runtime into the same stable pattern-address space used by RealitySlice.
    """
    normalized = [
        TemporalWorldCandidate(
            candidate_id=str(candidate_id),
            pattern_address=temporal_sensor_pattern_address(
                str(sensor_id),
                str(band_id),
            ),
        )
        for candidate_id, sensor_id, band_id in candidates
    ]
    normalized.sort(key=lambda item: item.candidate_id)
    return tuple(normalized)


def resolve_sensor_temporal_world_candidates(
    memory: StructuralTemporalObservationMemory,
    *,
    current_sensor_id: str,
    current_band_id: str,
    candidates: Iterable[tuple[str, str, str]],
    min_independent_slices: int = 3,
) -> TemporalWorldCandidateResolution:
    """Ask Memoria.ia to constrain only the concrete futures offered by the world."""
    return resolve_temporal_world_candidates(
        memory,
        temporal_sensor_pattern_address(current_sensor_id, current_band_id),
        make_temporal_world_candidates(candidates),
        min_independent_slices=min_independent_slices,
    )


def resolve_physical_sensor_future_set(
    memory: StructuralTemporalObservationMemory,
    *,
    current_sensor_id: str,
    current_band_id: str,
    future_set: EnvironmentalSensorFutureSet,
    sensor_id: str,
    min_independent_slices: int = 3,
) -> TemporalWorldCandidateResolution:
    """Constrain World Runtime-generated physical futures without caller-supplied bands."""
    selected = tuple(
        (
            candidate.candidate_id,
            candidate.sensor_id,
            candidate.band_id,
        )
        for candidate in future_set.candidates
        if candidate.sensor_id == sensor_id
    )
    if not selected:
        raise ValueError("physical future set does not contain requested sensor")
    return resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id=current_sensor_id,
        current_band_id=current_band_id,
        candidates=selected,
        min_independent_slices=min_independent_slices,
    )


def resolve_branching_physical_sensor_future_set(
    memory: StructuralTemporalObservationMemory,
    *,
    current_sensor_id: str,
    current_band_id: str,
    future_set: BranchingSensorFutureSet,
    sensor_id: str,
    min_independent_slices: int = 3,
) -> TemporalWorldCandidateResolution:
    """Constrain all world-generated branches for one sensor without selecting a branch."""
    selected = tuple(
        (
            candidate.candidate_id,
            candidate.sensor_id,
            candidate.band_id,
        )
        for candidate in future_set.candidates
        if candidate.sensor_id == sensor_id
    )
    if not selected:
        raise ValueError("branching future set does not contain requested sensor")
    return resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id=current_sensor_id,
        current_band_id=current_band_id,
        candidates=selected,
        min_independent_slices=min_independent_slices,
    )


def resolve_agent_conditioned_sensor_future_set(
    memory: StructuralTemporalObservationMemory,
    *,
    current_sensor_id: str,
    current_band_id: str,
    future_set: AgentConditionedSensorFutureSet,
    sensor_id: str,
    min_independent_slices: int = 3,
) -> TemporalWorldCandidateResolution:
    """Constrain a future already resolved by another autonomous world agent."""
    selected = tuple(
        (
            candidate.candidate_id,
            candidate.sensor_id,
            candidate.band_id,
        )
        for candidate in future_set.candidates
        if candidate.sensor_id == sensor_id
    )
    if not selected:
        raise ValueError("agent-conditioned future set does not contain requested sensor")
    return resolve_sensor_temporal_world_candidates(
        memory,
        current_sensor_id=current_sensor_id,
        current_band_id=current_band_id,
        candidates=selected,
        min_independent_slices=min_independent_slices,
    )
