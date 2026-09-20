from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DistributedEnvironmentalRule:
    rule_id: str
    agent_id: str
    min_ticks: int
    distribution_component: str
    region_retention_property: str
    region_evaporation_property: str
    route_capacity_property: str


@dataclass(frozen=True, slots=True)
class DistributedEnvironmentalTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    balances: tuple[dict[str, Any], ...]


def _agent_ids(world: dict[str, Any]) -> tuple[str, ...]:
    values = []
    for entity_id, entity in (world.get("entities") or {}).items():
        if (
            isinstance(entity, dict)
            and entity.get("status") == "active"
            and entity.get("class") == "environmental_agent"
        ):
            values.append(str(entity_id))
    return tuple(sorted(values))


def _rules(
    world: dict[str, Any],
    agent_id: str,
) -> tuple[DistributedEnvironmentalRule, ...]:
    parsed: list[DistributedEnvironmentalRule] = []
    for raw in (world.get("rules") or {}).get("environmental_distributed_agents") or ():
        if str(raw.get("agent") or "") != agent_id:
            continue
        rule_id = str(raw.get("rule_id") or "")
        component = str(raw.get("distribution_component") or "")
        retention = str(raw.get("region_retention_property") or "")
        evaporation = str(raw.get("region_evaporation_property") or "")
        capacity = str(raw.get("route_capacity_property") or "")
        min_ticks = int(raw.get("min_ticks", 1))
        if (
            not rule_id
            or not component
            or not retention
            or not evaporation
            or not capacity
        ):
            continue
        if min_ticks < 1:
            raise ValueError("distributed environmental min_ticks must be >= 1")
        parsed.append(
            DistributedEnvironmentalRule(
                rule_id=rule_id,
                agent_id=agent_id,
                min_ticks=min_ticks,
                distribution_component=component,
                region_retention_property=retention,
                region_evaporation_property=evaporation,
                route_capacity_property=capacity,
            )
        )
    parsed.sort(key=lambda item: item.rule_id)
    return tuple(parsed)


def _nonnegative_int(value: Any, *, label: str) -> int:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    integer = int(value)
    if integer < 0 or float(value) != float(integer):
        raise ValueError(f"{label} must be a non-negative integer")
    return integer


def _distribution(
    entity: dict[str, Any],
    component_name: str,
) -> tuple[dict[str, int], int, int]:
    component = ((entity.get("components") or {}).get(component_name) or {})
    raw = component.get("by_region") or {}
    by_region: dict[str, int] = {}
    for region_id, value in raw.items():
        amount = _nonnegative_int(value, label="distributed amount")
        if amount > 0:
            by_region[str(region_id)] = amount

    initial_total = _nonnegative_int(
        component.get("initial_total", sum(by_region.values())),
        label="initial_total",
    )
    evaporated_total = _nonnegative_int(
        component.get("evaporated_total", 0),
        label="evaporated_total",
    )
    if sum(by_region.values()) + evaporated_total != initial_total:
        raise ValueError("distributed environmental quantity is not conserved")
    return by_region, initial_total, evaporated_total


def _region_property(
    world: dict[str, Any],
    region_id: str,
    property_id: str,
) -> int:
    region = (world.get("regions") or {}).get(region_id) or {}
    properties = region.get("environmental_properties") or {}
    return _nonnegative_int(
        properties.get(property_id, 0),
        label=f"region property {property_id}",
    )


def _routes(
    world: dict[str, Any],
    region_id: str,
    capacity_property: str,
) -> tuple[tuple[str, str, int, str], ...]:
    region = (world.get("regions") or {}).get(region_id) or {}
    values: list[tuple[str, str, int, str]] = []
    for raw in region.get("environmental_routes") or ():
        if raw.get("available", True) is False:
            continue
        route_id = str((raw or {}).get("route_id") or "")
        to_region = str((raw or {}).get("to_region") or "")
        trace_address = str((raw or {}).get("trace_address") or "")
        if not route_id or not to_region or not trace_address:
            continue
        properties = raw.get("properties") or {}
        if capacity_property not in properties:
            continue
        capacity = _nonnegative_int(
            properties[capacity_property],
            label=f"route property {capacity_property}",
        )
        if capacity <= 0:
            continue
        values.append((route_id, to_region, capacity, trace_address))
    values.sort(key=lambda item: item[0])
    return tuple(values)


def _ready(
    entity: dict[str, Any],
    rule: DistributedEnvironmentalRule,
    *,
    candidate_tick: int,
) -> bool:
    state = ((entity.get("components") or {}).get("environmental_state") or {})
    last_tick = int(state.get("last_transition_tick", entity.get("created_at_tick", 0) or 0))
    return candidate_tick - last_tick >= rule.min_ticks


def advance_distributed_environmental_agents(
    world: dict[str, Any],
    *,
    ticks: int = 1,
) -> tuple[DistributedEnvironmentalTick, ...]:
    """Advance quantity-distributed environmental agents with exact integer balance.

    For every source region in the tick snapshot:
      before = retained + transferred + evaporated

    New inflows are not processed until the following logical tick.
    """
    if ticks < 1:
        raise ValueError("ticks must be >= 1")

    current = deepcopy(world)
    results: list[DistributedEnvironmentalTick] = []

    for _ in range(ticks):
        before_version = int(current.get("current_version", 0))
        before_tick = int(current.get("current_tick", 0))
        result_version = before_version + 1
        result_tick = before_tick + 1

        updated = deepcopy(current)
        operations: list[dict[str, Any]] = []
        balances: list[dict[str, Any]] = []

        for agent_id in _agent_ids(current):
            entity_before = current["entities"][agent_id]
            matching = _rules(current, agent_id)
            if not matching:
                continue
            rule = matching[0]
            if not _ready(entity_before, rule, candidate_tick=result_tick):
                continue

            by_region, initial_total, evaporated_total = _distribution(
                entity_before,
                rule.distribution_component,
            )
            next_distribution: dict[str, int] = {}
            evaporated_this_tick = 0

            for region_id in sorted(by_region):
                amount_before = by_region[region_id]
                evaporation_limit = _region_property(
                    current,
                    region_id,
                    rule.region_evaporation_property,
                )
                evaporated = min(amount_before, evaporation_limit)
                after_evaporation = amount_before - evaporated

                retention_target = _region_property(
                    current,
                    region_id,
                    rule.region_retention_property,
                )
                retained_base = min(after_evaporation, retention_target)
                mobile = after_evaporation - retained_base

                transfers: list[dict[str, Any]] = []
                transferred_total = 0
                for route_id, to_region, capacity, trace_address in _routes(
                    current,
                    region_id,
                    rule.route_capacity_property,
                ):
                    if mobile <= 0:
                        break
                    moved = min(mobile, capacity)
                    if moved <= 0:
                        continue
                    mobile -= moved
                    transferred_total += moved
                    next_distribution[to_region] = next_distribution.get(to_region, 0) + moved
                    transfers.append(
                        {
                            "route_id": route_id,
                            "to_region": to_region,
                            "amount": moved,
                            "capacity": capacity,
                            "trace_address": trace_address,
                        }
                    )

                # Unused mobile quantity remains in the source region.
                retained_total = retained_base + mobile
                if retained_total > 0:
                    next_distribution[region_id] = next_distribution.get(region_id, 0) + retained_total

                evaporated_this_tick += evaporated
                if retained_total + transferred_total + evaporated != amount_before:
                    raise AssertionError("distributed environmental tick lost quantity")

                balances.append(
                    {
                        "agent_id": agent_id,
                        "region_id": region_id,
                        "before": amount_before,
                        "retained": retained_total,
                        "transferred": transferred_total,
                        "evaporated": evaporated,
                        "transfers": tuple(deepcopy(transfers)),
                    }
                )

            new_evaporated_total = evaporated_total + evaporated_this_tick
            if sum(next_distribution.values()) + new_evaporated_total != initial_total:
                raise AssertionError("distributed environmental total is not conserved")

            entity = updated["entities"][agent_id]
            components = entity.setdefault("components", {})
            distribution_component = components.setdefault(rule.distribution_component, {})
            distribution_component["initial_total"] = initial_total
            distribution_component["by_region"] = dict(sorted(next_distribution.items()))
            distribution_component["evaporated_total"] = new_evaporated_total

            state = components.setdefault("environmental_state", {})
            state["last_transition_tick"] = result_tick
            state["generation"] = int(state.get("generation", 0)) + 1
            entity["version"] = result_version

            operations.extend(
                [
                    {
                        "op": "set",
                        "path": f"/entities/{agent_id}/components/{rule.distribution_component}",
                        "value": deepcopy(distribution_component),
                    },
                    {
                        "op": "set",
                        "path": f"/entities/{agent_id}/components/environmental_state",
                        "value": deepcopy(state),
                    },
                ]
            )

        delta_id = f"delta_{result_version:08d}"
        event_id = f"event_{result_tick:08d}_environment_distributed"
        delta = {
            "delta_id": delta_id,
            "base_version": before_version,
            "result_version": result_version,
            "tick_id": result_tick,
            "operations": deepcopy(operations),
            "provenance": {"origin": "environmental-distributed-runtime"},
        }
        event = {
            "event_id": event_id,
            "tick_id": result_tick,
            "type": "environmental_distributed_tick",
            "actor": None,
            "targets": sorted({item["agent_id"] for item in balances}),
            "before": {"version": before_version, "tick": before_tick},
            "after": {
                "version": result_version,
                "tick": result_tick,
                "region_balance_count": len(balances),
            },
            "balances": deepcopy(balances),
            "delta_id": delta_id,
            "provenance": {
                "origin": "environmental-distributed-runtime",
                "processed_by": "environmental-distributed-runtime",
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

        current = updated
        results.append(
            DistributedEnvironmentalTick(
                world=deepcopy(updated),
                event=event,
                delta=delta,
                balances=tuple(deepcopy(balances)),
            )
        )

    return tuple(results)
