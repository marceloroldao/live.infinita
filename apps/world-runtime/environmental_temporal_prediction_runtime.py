from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from memoria_resolutiva.structural_temporal_recall_v2 import (
    TemporalWorldCandidateResolution,
)

from environmental_future_runtime import (
    EnvironmentalSensorFutureSet,
    enumerate_next_distributed_sensor_candidates,
)
from temporal_prediction_memoria_adapter import resolve_physical_sensor_future_set


@dataclass(frozen=True, slots=True)
class EnvironmentalTemporalPrediction:
    observer_id: str
    sensor_id: str
    current_band_id: str
    physical_futures: EnvironmentalSensorFutureSet
    resolution: TemporalWorldCandidateResolution


def _current_sensor_band(
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_id: str,
) -> str:
    observer = (world.get("entities") or {}).get(observer_id) or {}
    reading = (
        ((observer.get("components") or {}).get("sensor_state") or {})
        .get("readings", {})
        .get(sensor_id)
    )
    if not isinstance(reading, dict):
        raise ValueError("current sensor reading is required before temporal prediction")
    band_id = str(reading.get("band_id") or "")
    if not band_id:
        raise ValueError("current sensor reading must contain a committed band_id")
    return band_id


def predict_next_environmental_sensor(
    memory: StructuralTemporalObservationMemory,
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_id: str,
    min_independent_slices: int = 3,
) -> EnvironmentalTemporalPrediction:
    """Preview real physics first, then let Memoria.ia constrain that concrete set."""
    current_band_id = _current_sensor_band(
        world,
        observer_id=observer_id,
        sensor_id=sensor_id,
    )
    physical_futures = enumerate_next_distributed_sensor_candidates(
        world,
        observer_id=observer_id,
        sensor_ids=(sensor_id,),
    )
    resolution = resolve_physical_sensor_future_set(
        memory,
        current_sensor_id=sensor_id,
        current_band_id=current_band_id,
        future_set=physical_futures,
        sensor_id=sensor_id,
        min_independent_slices=min_independent_slices,
    )
    return EnvironmentalTemporalPrediction(
        observer_id=observer_id,
        sensor_id=sensor_id,
        current_band_id=current_band_id,
        physical_futures=physical_futures,
        resolution=resolution,
    )
