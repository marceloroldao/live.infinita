from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from reality_slice import Modality, Occurrence, RealitySlice, TemporalAssociator


@dataclass(frozen=True, slots=True)
class SensorPattern:
    sensor_id: str
    band_id: str
    pattern_id: int


@dataclass(frozen=True, slots=True)
class RealityWindow:
    frame_ids: tuple[str, ...]
    frame_ticks: tuple[int, ...]
    patterns: tuple[SensorPattern, ...]
    reality_slice: RealitySlice


def _stable_int(value: str, *, bits: int = 63) -> int:
    digest = sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << bits) - 1)


def sensor_pattern_id(sensor_id: str, band_id: str) -> int:
    if not sensor_id or not band_id:
        raise ValueError("sensor_id and band_id must be non-empty")
    # Pattern identity depends only on observable channel identity + opaque band.
    return _stable_int(f"sensor-pattern|{sensor_id}|{band_id}")


def _multisensor_events(
    world: dict[str, Any],
    *,
    observer_id: str,
) -> tuple[dict[str, Any], ...]:
    events = []
    for event in (world.get("events") or {}).values():
        if (
            isinstance(event, dict)
            and event.get("type") == "multimodal_sensor_frame_sampled"
            and str(event.get("actor") or "") == observer_id
            and str(event.get("frame_id") or "")
        ):
            events.append(event)
    events.sort(
        key=lambda item: (
            int(item.get("tick_id", -1)),
            str(item.get("event_id") or ""),
        )
    )
    return tuple(events)


def reality_window_from_world(
    world: dict[str, Any],
    *,
    observer_id: str,
    frame_count: int = 3,
    tick_seconds: float = 0.10,
    occurrence_duration: float = 0.02,
) -> RealityWindow:
    """Convert the latest synchronized sensor frames into one temporal RealitySlice.

    No semantic relation is added. Each committed sensor band becomes one opaque
    SENSOR occurrence. World logical tick distance is preserved through tick_seconds.
    """
    if frame_count < 2:
        raise ValueError("frame_count must be >= 2")
    if tick_seconds <= 0 or occurrence_duration <= 0:
        raise ValueError("time scales must be positive")

    events = _multisensor_events(world, observer_id=observer_id)
    if len(events) < frame_count:
        raise ValueError("not enough multimodal sensor frames")
    selected = events[-frame_count:]

    base_tick = int(selected[0]["tick_id"])
    frame_ids = tuple(str(event["frame_id"]) for event in selected)
    frame_ticks = tuple(int(event["tick_id"]) for event in selected)
    slice_seed = "|".join([observer_id, *frame_ids])
    slice_id = _stable_int(f"reality-slice|{slice_seed}")

    occurrences: list[Occurrence] = []
    patterns: dict[tuple[str, str], SensorPattern] = {}

    for event in selected:
        event_tick = int(event["tick_id"])
        t_start = (event_tick - base_tick) * tick_seconds
        t_end = t_start + occurrence_duration
        frame_id = str(event["frame_id"])
        provenance = _stable_int(f"frame-provenance|{frame_id}", bits=31)

        channels = sorted(
            (event.get("channels") or ()),
            key=lambda item: (
                str((item or {}).get("sensor_id") or ""),
                str((item or {}).get("band_id") or ""),
            ),
        )
        for channel in channels:
            sensor_id = str((channel or {}).get("sensor_id") or "")
            band_id = str((channel or {}).get("band_id") or "")
            if not sensor_id or not band_id:
                continue
            pattern_id = sensor_pattern_id(sensor_id, band_id)
            patterns[(sensor_id, band_id)] = SensorPattern(
                sensor_id=sensor_id,
                band_id=band_id,
                pattern_id=pattern_id,
            )
            occurrences.append(
                Occurrence(
                    pattern=pattern_id,
                    modality=Modality.SENSOR,
                    t_start=t_start,
                    t_end=t_end,
                    source=_stable_int(f"sensor-source|{sensor_id}", bits=31),
                    provenance=provenance,
                )
            )

    if not occurrences:
        raise ValueError("selected frames contain no sensor channels")

    slice_start = 0.0
    slice_end = max(item.t_end for item in occurrences)
    reality_slice = RealitySlice(
        slice_id=slice_id,
        t_start=slice_start,
        t_end=slice_end,
        occurrences=tuple(
            sorted(
                occurrences,
                key=lambda item: (
                    item.t_start,
                    item.pattern,
                    item.source,
                ),
            )
        ),
        provenance=tuple(
            _stable_int(f"frame-provenance|{frame_id}", bits=31)
            for frame_id in frame_ids
        ),
    )
    return RealityWindow(
        frame_ids=frame_ids,
        frame_ticks=frame_ticks,
        patterns=tuple(
            sorted(patterns.values(), key=lambda item: (item.sensor_id, item.band_id))
        ),
        reality_slice=reality_slice,
    )


def ingest_reality_windows(
    engine: TemporalAssociator,
    windows: Iterable[RealityWindow],
) -> TemporalAssociator:
    for window in windows:
        engine.ingest(window.reality_slice)
    return engine
