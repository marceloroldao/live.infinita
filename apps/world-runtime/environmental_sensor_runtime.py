from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class SensorSample:
    sensor_id: str
    observer_id: str
    target_id: str
    region_id: str
    raw_value: int
    noisy_value: int
    candidate_band_id: str
    committed_band_id: str
    pending_band_id: str | None
    pending_count: int


@dataclass(frozen=True, slots=True)
class SensorTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    samples: tuple[SensorSample, ...]


def _observer_region(world: dict[str, Any], observer_id: str) -> str | None:
    entity = (world.get("entities") or {}).get(observer_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        return None
    value = ((entity.get("components") or {}).get("transform") or {}).get("region_id")
    return str(value) if value is not None else None


def _sensor_rules(world: dict[str, Any], observer_id: str) -> tuple[dict[str, Any], ...]:
    values = []
    for raw in (world.get("rules") or {}).get("environmental_sensors") or ():
        if str(raw.get("observer") or "") != observer_id:
            continue
        sensor_id = str(raw.get("sensor_id") or "")
        target = str(raw.get("target") or "")
        source_component = str(raw.get("source_component") or "")
        if not sensor_id or not target or not source_component:
            continue
        values.append(deepcopy(raw))
    values.sort(key=lambda item: str(item["sensor_id"]))
    return tuple(values)


def _local_quantity(
    world: dict[str, Any],
    *,
    target_id: str,
    source_component: str,
    region_id: str,
) -> int:
    target = (world.get("entities") or {}).get(target_id)
    if not isinstance(target, dict) or target.get("status") != "active":
        return 0
    component = ((target.get("components") or {}).get(source_component) or {})
    value = (component.get("by_region") or {}).get(region_id, 0)
    if not isinstance(value, (int, float)):
        raise ValueError("sensor source quantity must be numeric")
    integer = int(value)
    if integer < 0 or float(value) != float(integer):
        raise ValueError("sensor source quantity must be a non-negative integer")
    return integer


def _deterministic_noise(
    *,
    world_id: str,
    sensor_id: str,
    observer_id: str,
    tick_id: int,
    raw_value: int,
    amplitude: int,
) -> int:
    if amplitude < 0:
        raise ValueError("noise_amplitude must be >= 0")
    if amplitude == 0:
        return 0
    digest = sha256(
        f"{world_id}|{sensor_id}|{observer_id}|{tick_id}|{raw_value}".encode("utf-8")
    ).digest()
    span = amplitude * 2 + 1
    return int.from_bytes(digest[:8], "big") % span - amplitude


def _bands(rule: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    parsed = []
    for raw in rule.get("bands") or ():
        band_id = str((raw or {}).get("band_id") or "")
        min_value = (raw or {}).get("min_value")
        if not band_id or not isinstance(min_value, (int, float)):
            continue
        integer = int(min_value)
        if integer < 0 or float(min_value) != float(integer):
            raise ValueError("sensor band min_value must be a non-negative integer")
        parsed.append((band_id, integer))
    parsed.sort(key=lambda item: (item[1], item[0]))
    if not parsed:
        raise ValueError("sensor requires at least one band")
    if parsed[0][1] != 0:
        raise ValueError("sensor first band must start at 0")
    if len({item[0] for item in parsed}) != len(parsed):
        raise ValueError("sensor band_id must be unique")
    return tuple(parsed)


def _band_index(bands: tuple[tuple[str, int], ...], value: int) -> int:
    index = 0
    for i, (_band_id, minimum) in enumerate(bands):
        if value >= minimum:
            index = i
        else:
            break
    return index


def _candidate_with_hysteresis(
    *,
    bands: tuple[tuple[str, int], ...],
    noisy_value: int,
    current_band_id: str | None,
    hysteresis: int,
) -> str:
    if hysteresis < 0:
        raise ValueError("hysteresis must be >= 0")

    raw_index = _band_index(bands, noisy_value)
    if current_band_id is None:
        return bands[raw_index][0]

    indexes = {band_id: i for i, (band_id, _minimum) in enumerate(bands)}
    if current_band_id not in indexes:
        return bands[raw_index][0]
    current_index = indexes[current_band_id]

    if raw_index > current_index:
        boundary = bands[current_index + 1][1]
        if noisy_value < boundary + hysteresis:
            return current_band_id
    elif raw_index < current_index:
        boundary = bands[current_index][1]
        if noisy_value >= max(0, boundary - hysteresis):
            return current_band_id
    return bands[raw_index][0]


def _commit_with_persistence(
    *,
    current_band_id: str | None,
    pending_band_id: str | None,
    pending_count: int,
    candidate_band_id: str,
    persistence_samples: int,
) -> tuple[str, str | None, int]:
    if persistence_samples < 1:
        raise ValueError("persistence_samples must be >= 1")

    if current_band_id is None:
        return candidate_band_id, None, 0
    if candidate_band_id == current_band_id:
        return current_band_id, None, 0

    if pending_band_id == candidate_band_id:
        next_count = pending_count + 1
    else:
        next_count = 1

    if next_count >= persistence_samples:
        return candidate_band_id, None, 0
    return current_band_id, candidate_band_id, next_count


def sample_environmental_sensors(
    world: dict[str, Any],
    *,
    observer_id: str,
) -> SensorTick:
    """Authoritatively sample hidden environmental quantities into coarse sensor bands."""
    region_id = _observer_region(world, observer_id)
    if region_id is None:
        raise ValueError("observer must exist, be active and have a region")

    before_version = int(world.get("current_version", 0))
    before_tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = before_tick + 1

    updated = deepcopy(world)
    observer = updated["entities"][observer_id]
    sensor_state = observer.setdefault("components", {}).setdefault("sensor_state", {})
    readings = sensor_state.setdefault("readings", {})

    operations: list[dict[str, Any]] = []
    samples: list[SensorSample] = []

    for rule in _sensor_rules(world, observer_id):
        sensor_id = str(rule["sensor_id"])
        target_id = str(rule["target"])
        source_component = str(rule["source_component"])
        bands = _bands(rule)
        noise_amplitude = int(rule.get("noise_amplitude", 0))
        hysteresis = int(rule.get("hysteresis", 0))
        persistence_samples = int(rule.get("persistence_samples", 1))

        raw_value = _local_quantity(
            world,
            target_id=target_id,
            source_component=source_component,
            region_id=region_id,
        )
        noise = _deterministic_noise(
            world_id=str(world.get("world_id") or ""),
            sensor_id=sensor_id,
            observer_id=observer_id,
            tick_id=result_tick,
            raw_value=raw_value,
            amplitude=noise_amplitude,
        )
        noisy_value = max(0, raw_value + noise)

        previous = deepcopy(readings.get(sensor_id) or {})
        current_band_id = previous.get("band_id")
        pending_band_id = previous.get("pending_band_id")
        pending_count = int(previous.get("pending_count", 0) or 0)

        candidate_band_id = _candidate_with_hysteresis(
            bands=bands,
            noisy_value=noisy_value,
            current_band_id=str(current_band_id) if current_band_id else None,
            hysteresis=hysteresis,
        )
        committed, next_pending, next_pending_count = _commit_with_persistence(
            current_band_id=str(current_band_id) if current_band_id else None,
            pending_band_id=str(pending_band_id) if pending_band_id else None,
            pending_count=pending_count,
            candidate_band_id=candidate_band_id,
            persistence_samples=persistence_samples,
        )

        readings[sensor_id] = {
            "sensor_id": sensor_id,
            "target_id": target_id,
            "region_id": region_id,
            "band_id": committed,
            "pending_band_id": next_pending,
            "pending_count": next_pending_count,
            "sampled_tick": result_tick,
            # Raw/noisy values remain authoritative hidden state and are never projected.
            "raw_value": raw_value,
            "noisy_value": noisy_value,
        }

        operations.append(
            {
                "op": "set",
                "path": f"/entities/{observer_id}/components/sensor_state/readings/{sensor_id}",
                "value": deepcopy(readings[sensor_id]),
            }
        )
        samples.append(
            SensorSample(
                sensor_id=sensor_id,
                observer_id=observer_id,
                target_id=target_id,
                region_id=region_id,
                raw_value=raw_value,
                noisy_value=noisy_value,
                candidate_band_id=candidate_band_id,
                committed_band_id=committed,
                pending_band_id=next_pending,
                pending_count=next_pending_count,
            )
        )

    observer["version"] = result_version
    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_sensor_sample"
    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": deepcopy(operations),
        "provenance": {
            "origin": "environmental-sensor-runtime",
            "observer_id": observer_id,
        },
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "environmental_sensor_sampled",
        "actor": observer_id,
        "targets": [sample.target_id for sample in samples],
        "before": {"version": before_version, "tick": before_tick},
        "after": {
            "version": result_version,
            "tick": result_tick,
            "sample_count": len(samples),
        },
        "samples": [
            {
                "sensor_id": sample.sensor_id,
                "target_id": sample.target_id,
                "region_id": sample.region_id,
                "band_id": sample.committed_band_id,
                "pending_band_id": sample.pending_band_id,
                "pending_count": sample.pending_count,
            }
            for sample in samples
        ],
        "delta_id": delta_id,
        "provenance": {
            "origin": "environmental-sensor-runtime",
            "processed_by": "environmental-sensor-runtime",
        },
    }

    updated.setdefault("deltas", {})[delta_id] = deepcopy(delta)
    updated.setdefault("events", {})[event_id] = deepcopy(event)
    updated.setdefault("versions", {})[str(result_version)] = {
        "parent_version": before_version,
        "delta_id": delta_id,
    }
    updated["current_version"] = result_version
    updated["current_tick"] = result_tick

    return SensorTick(
        world=updated,
        event=event,
        delta=delta,
        samples=tuple(samples),
    )


def project_environmental_sensor_readings(
    world: dict[str, Any],
    observer_id: str,
) -> dict[str, Any]:
    """Project committed sensor bands as opaque read-only cognitive entities."""
    projected = deepcopy(world)
    observer = (projected.get("entities") or {}).get(observer_id)
    if not isinstance(observer, dict) or observer.get("status") != "active":
        return projected

    readings = (
        ((observer.get("components") or {}).get("sensor_state") or {}).get("readings") or {}
    )
    entities = projected.setdefault("entities", {})
    relations = projected.setdefault("relations", {})

    for sensor_id in sorted(readings):
        reading = readings[sensor_id] or {}
        band_id = str(reading.get("band_id") or "")
        target_id = str(reading.get("target_id") or "")
        region_id = str(reading.get("region_id") or "")
        if not band_id or not target_id or not region_id:
            continue

        # Reading identity encodes only the committed band, never raw/noisy quantity.
        reading_digest = sha256(f"{sensor_id}|{band_id}".encode("utf-8")).hexdigest()[:16]
        reading_entity_id = f"sensor_reading_{reading_digest}"
        relation_digest = sha256(
            f"{observer_id}|{sensor_id}|sensor-reading".encode("utf-8")
        ).hexdigest()[:16]
        relation_id = f"rel_sensor_{relation_digest}"

        entities[reading_entity_id] = {
            "entity_id": reading_entity_id,
            "class": "sensor_reading",
            "type": "environmental_sensor_band",
            "status": "active",
            "version": int(projected.get("current_version", 0)),
            "created_at_tick": int(reading.get("sampled_tick", projected.get("current_tick", 0))),
            "components": {
                "sensor": {"sensor_id": sensor_id},
                "target": {"entity_id": target_id},
                "region": {"region_id": region_id},
            },
        }
        relations[relation_id] = {
            "relation_id": relation_id,
            "subject": observer_id,
            "predicate": "senses",
            "object": reading_entity_id,
            "status": "active",
            "confidence": 1.0,
            "valid_from_tick": int(reading.get("sampled_tick", projected.get("current_tick", 0))),
            "valid_until_tick": None,
            "source": {"type": "environmental-sensor-projection", "sensor_id": sensor_id},
            "version": int(projected.get("current_version", 0)),
        }

    return projected
