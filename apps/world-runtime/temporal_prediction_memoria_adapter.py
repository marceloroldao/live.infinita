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
