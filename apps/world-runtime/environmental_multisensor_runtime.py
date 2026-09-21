from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class MultiSensorSample:
    sensor_id: str
    channel_kind: str
    target_id: str
    region_id: str
    band_id: str
    raw_value: str
    frame_id: str


@dataclass(frozen=True, slots=True)
class MultiSensorTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    frame_id: str
    samples: tuple[MultiSensorSample, ...]


def _observer_region(world: dict[str, Any], observer_id: str) -> str:
    entity = (world.get("entities") or {}).get(observer_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        raise ValueError("observer must exist and be active")
    value = ((entity.get("components") or {}).get("transform") or {}).get("region_id")
    if value is None:
        raise ValueError("observer must have region_id")
    return str(value)


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
        raise ValueError("multisensor source quantity must be numeric")
    integer = int(value)
    if integer < 0 or float(value) != float(integer):
        raise ValueError("multisensor source quantity must be a non-negative integer")
    return integer


def _component_enum_value(
    world: dict[str, Any],
    *,
    target_id: str,
    source_component: str,
    source_field: str,
) -> str:
    target = (world.get("entities") or {}).get(target_id)
    if not isinstance(target, dict) or target.get("status") != "active":
        raise ValueError("component enum target must exist and be active")
    component = ((target.get("components") or {}).get(source_component) or {})
    value = component.get(source_field)
    if value is None:
        raise ValueError("component enum source field is missing")
    return str(value)


def _band_from_thresholds(channel: dict[str, Any], value: int) -> str:
    bands = []
    for raw in channel.get("bands") or ():
        band_id = str((raw or {}).get("band_id") or "")
        minimum = (raw or {}).get("min_value")
        if not band_id or not isinstance(minimum, (int, float)):
            continue
        bands.append((band_id, int(minimum)))
    bands.sort(key=lambda item: (item[1], item[0]))
    if not bands or bands[0][1] != 0:
        raise ValueError("threshold channel requires a band starting at zero")
    chosen = bands[0][0]
    for band_id, minimum in bands:
        if value >= minimum:
            chosen = band_id
        else:
            break
    return chosen


def _latest_distributed_balance(
    world: dict[str, Any],
    *,
    target_id: str,
    region_id: str,
) -> dict[str, Any] | None:
    events = sorted(
        (world.get("events") or {}).values(),
        key=lambda item: (int((item or {}).get("tick_id", -1)), str((item or {}).get("event_id") or "")),
        reverse=True,
    )
    for event in events:
        if (event or {}).get("type") != "environmental_distributed_tick":
            continue
        for balance in (event or {}).get("balances") or ():
            if (
                str((balance or {}).get("agent_id") or "") == target_id
                and str((balance or {}).get("region_id") or "") == region_id
            ):
                return deepcopy(balance)
    return None


def _channel_band(
    world: dict[str, Any],
    *,
    channel: dict[str, Any],
    observer_id: str,
    region_id: str,
    previous: dict[str, Any] | None,
) -> tuple[str, str]:
    kind = str(channel.get("kind") or "")
    target_id = str(channel.get("target") or "")
    source_component = str(channel.get("source_component") or "environmental_distribution")

    if kind == "component_enum":
        source_field = str(channel.get("source_field") or "")
        value_bands = {
            str(value): str(band_id)
            for value, band_id in (channel.get("value_band_ids") or {}).items()
            if str(value) and str(band_id)
        }
        if not source_component or not source_field or not value_bands:
            raise ValueError(
                "component_enum requires source_component, source_field and value_band_ids"
            )
        value = _component_enum_value(
            world,
            target_id=target_id,
            source_component=source_component,
            source_field=source_field,
        )
        band_id = value_bands.get(value)
        if not band_id:
            unknown_band = str(channel.get("unknown_band_id") or "")
            if not unknown_band:
                raise ValueError("component_enum value has no configured band")
            band_id = unknown_band
        return band_id, value

    quantity = _local_quantity(
        world,
        target_id=target_id,
        source_component=source_component,
        region_id=region_id,
    )

    if kind == "presence":
        present_band = str(channel.get("present_band_id") or "")
        absent_band = str(channel.get("absent_band_id") or "")
        if not present_band or not absent_band:
            raise ValueError("presence channel requires present/absent bands")
        return (present_band if quantity > 0 else absent_band), str(1 if quantity > 0 else 0)

    if kind == "intensity":
        return _band_from_thresholds(channel, quantity), str(quantity)

    if kind == "trend":
        stable_band = str(channel.get("stable_band_id") or "")
        rising_band = str(channel.get("rising_band_id") or "")
        falling_band = str(channel.get("falling_band_id") or "")
        deadband = int(channel.get("deadband", 0))
        if not stable_band or not rising_band or not falling_band or deadband < 0:
            raise ValueError("trend channel configuration is invalid")

        previous_quantity = None
        if previous is not None:
            raw = previous.get("source_value")
            if isinstance(raw, (int, float)):
                previous_quantity = int(raw)
        if previous_quantity is None:
            return stable_band, str(quantity)

        delta = quantity - previous_quantity
        if delta > deadband:
            return rising_band, str(delta)
        if delta < -deadband:
            return falling_band, str(delta)
        return stable_band, str(delta)

    if kind == "dominant_transfer":
        none_band = str(channel.get("none_band_id") or "")
        route_bands = {
            str(route_id): str(band_id)
            for route_id, band_id in (channel.get("route_band_ids") or {}).items()
            if str(route_id) and str(band_id)
        }
        if not none_band:
            raise ValueError("dominant_transfer requires none_band_id")
        balance = _latest_distributed_balance(
            world,
            target_id=target_id,
            region_id=region_id,
        )
        if balance is None:
            return none_band, "none"
        transfers = tuple(balance.get("transfers") or ())
        if not transfers:
            return none_band, "none"
        ranked = sorted(
            transfers,
            key=lambda item: (
                -int((item or {}).get("amount", 0)),
                str((item or {}).get("route_id") or ""),
            ),
        )
        route_id = str(ranked[0].get("route_id") or "")
        return route_bands.get(route_id, none_band), route_id or "none"

    raise ValueError(f"unsupported multisensor channel kind: {kind}")


def sample_multimodal_sensor_frame(
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_ids: Iterable[str] | None = None,
) -> MultiSensorTick:
    """Sample independent environmental channels into one synchronized sensor frame."""
    region_id = _observer_region(world, observer_id)
    requested = None
    if sensor_ids is not None:
        requested = {str(value) for value in sensor_ids}
        if not requested or "" in requested:
            raise ValueError("sensor_ids must contain non-empty values")

    rules = [
        deepcopy(raw)
        for raw in (world.get("rules") or {}).get("multimodal_sensors") or ()
        if str((raw or {}).get("observer") or "") == observer_id
        and (
            requested is None
            or str((raw or {}).get("sensor_id") or "") in requested
        )
    ]
    rules.sort(key=lambda item: str(item.get("sensor_id") or ""))
    if not rules:
        raise ValueError("observer has no selected multimodal sensor channels")
    if requested is not None:
        found = {str(item.get("sensor_id") or "") for item in rules}
        missing = tuple(sorted(requested - found))
        if missing:
            raise ValueError(f"requested sensors are not configured: {missing}")

    before_version = int(world.get("current_version", 0))
    before_tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = before_tick + 1
    frame_seed = f"{world.get('world_id','')}|{observer_id}|{result_tick}|{region_id}"
    frame_id = "sensor_frame_" + sha256(frame_seed.encode("utf-8")).hexdigest()[:20]

    updated = deepcopy(world)
    observer = updated["entities"][observer_id]
    sensor_state = observer.setdefault("components", {}).setdefault("sensor_state", {})
    readings = sensor_state.setdefault("readings", {})

    operations: list[dict[str, Any]] = []
    samples: list[MultiSensorSample] = []

    for channel in rules:
        sensor_id = str(channel.get("sensor_id") or "")
        target_id = str(channel.get("target") or "")
        kind = str(channel.get("kind") or "")
        if not sensor_id or not target_id or not kind:
            raise ValueError("multimodal channel requires sensor_id, target and kind")

        previous = deepcopy(readings.get(sensor_id) or {})
        band_id, raw_value = _channel_band(
            world,
            channel=channel,
            observer_id=observer_id,
            region_id=region_id,
            previous=previous,
        )
        source_component = str(channel.get("source_component") or "environmental_distribution")
        if kind == "component_enum":
            source_value: Any = _component_enum_value(
                world,
                target_id=target_id,
                source_component=source_component,
                source_field=str(channel.get("source_field") or ""),
            )
        else:
            source_value = _local_quantity(
                world,
                target_id=target_id,
                source_component=source_component,
                region_id=region_id,
            )

        readings[sensor_id] = {
            "sensor_id": sensor_id,
            "target_id": target_id,
            "region_id": region_id,
            "band_id": band_id,
            "sampled_tick": result_tick,
            "frame_id": frame_id,
            "channel_kind": kind,
            "source_value": source_value,
            "raw_value": raw_value,
        }
        operations.append(
            {
                "op": "set",
                "path": f"/entities/{observer_id}/components/sensor_state/readings/{sensor_id}",
                "value": deepcopy(readings[sensor_id]),
            }
        )
        samples.append(
            MultiSensorSample(
                sensor_id=sensor_id,
                channel_kind=kind,
                target_id=target_id,
                region_id=region_id,
                band_id=band_id,
                raw_value=raw_value,
                frame_id=frame_id,
            )
        )

    sensor_state["current_frame_id"] = frame_id
    sensor_state["current_frame_tick"] = result_tick
    observer["version"] = result_version
    operations.append(
        {
            "op": "set",
            "path": f"/entities/{observer_id}/components/sensor_state/current_frame_id",
            "value": frame_id,
        }
    )

    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_multimodal_sensor"
    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": deepcopy(operations),
        "provenance": {
            "origin": "multimodal-sensor-runtime",
            "observer_id": observer_id,
            "frame_id": frame_id,
        },
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "multimodal_sensor_frame_sampled",
        "actor": observer_id,
        "targets": sorted({sample.target_id for sample in samples}),
        "frame_id": frame_id,
        "channels": [
            {
                "sensor_id": sample.sensor_id,
                "channel_kind": sample.channel_kind,
                "band_id": sample.band_id,
            }
            for sample in samples
        ],
        "before": {"version": before_version, "tick": before_tick},
        "after": {
            "version": result_version,
            "tick": result_tick,
            "channel_count": len(samples),
        },
        "delta_id": delta_id,
        "provenance": {
            "origin": "multimodal-sensor-runtime",
            "processed_by": "multimodal-sensor-runtime",
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

    return MultiSensorTick(
        world=updated,
        event=event,
        delta=delta,
        frame_id=frame_id,
        samples=tuple(samples),
    )
