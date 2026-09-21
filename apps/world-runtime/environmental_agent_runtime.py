from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class EnvironmentalTransitionRule:
    rule_id: str
    agent_id: str
    from_region: str
    to_region: str
    min_ticks: int
    trace_address: str


@dataclass(frozen=True, slots=True)
class EnvironmentalTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    transitions: tuple[dict[str, Any], ...]


def _rules(world: dict[str, Any], agent_id: str) -> tuple[EnvironmentalTransitionRule, ...]:
    parsed: list[EnvironmentalTransitionRule] = []
    for raw in (world.get("rules") or {}).get("environmental_agents") or ():
        if str(raw.get("agent") or "") != agent_id:
            continue
        rule_id = str(raw.get("rule_id") or "")
        from_region = str(raw.get("from_region") or "")
        to_region = str(raw.get("to_region") or "")
        trace_address = str(raw.get("trace_address") or "")
        min_ticks = int(raw.get("min_ticks", 1))
        if not rule_id or not from_region or not to_region or not trace_address:
            continue
        if min_ticks < 1:
            raise ValueError("environmental min_ticks must be >= 1")
        parsed.append(
            EnvironmentalTransitionRule(
                rule_id=rule_id,
                agent_id=agent_id,
                from_region=from_region,
                to_region=to_region,
                min_ticks=min_ticks,
                trace_address=trace_address,
            )
        )
    parsed.sort(key=lambda item: item.rule_id)
    return tuple(parsed)


def environmental_agent_ids(world: dict[str, Any]) -> tuple[str, ...]:
    ids = []
    for entity_id, entity in (world.get("entities") or {}).items():
        if (
            isinstance(entity, dict)
            and entity.get("status") == "active"
            and entity.get("class") == "environmental_agent"
        ):
            ids.append(str(entity_id))
    return tuple(sorted(ids))


def _region(entity: dict[str, Any]) -> str | None:
    value = ((entity.get("components") or {}).get("transform") or {}).get("region_id")
    return str(value) if value is not None else None


def _ready_rule(
    world: dict[str, Any],
    agent_id: str,
    *,
    candidate_tick: int,
) -> EnvironmentalTransitionRule | None:
    entity = (world.get("entities") or {}).get(agent_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        return None

    region_id = _region(entity)
    state = ((entity.get("components") or {}).get("environmental_state") or {})
    last_tick = int(state.get("last_transition_tick", entity.get("created_at_tick", 0) or 0))

    candidates = [
        rule
        for rule in _rules(world, agent_id)
        if rule.from_region == region_id and candidate_tick - last_tick >= rule.min_ticks
    ]
    return candidates[0] if candidates else None


def advance_environmental_agents(
    world: dict[str, Any],
    *,
    ticks: int = 1,
) -> tuple[EnvironmentalTick, ...]:
    """Advance world-owned environmental agents on logical ticks.

    Each call is deterministic and independent of any observer action. Every logical
    tick creates one authoritative Event/Delta, even when no agent transitions.
    """
    if ticks < 1:
        raise ValueError("ticks must be >= 1")

    current = deepcopy(world)
    results: list[EnvironmentalTick] = []

    for _ in range(ticks):
        before_version = int(current.get("current_version", 0))
        before_tick = int(current.get("current_tick", 0))
        result_version = before_version + 1
        result_tick = before_tick + 1

        updated = deepcopy(current)
        operations: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []

        for agent_id in environmental_agent_ids(current):
            rule = _ready_rule(current, agent_id, candidate_tick=result_tick)
            if rule is None:
                continue

            entity = updated["entities"][agent_id]
            components = entity.setdefault("components", {})
            transform = components.setdefault("transform", {})
            state = components.setdefault("environmental_state", {})
            generation = int(state.get("generation", 0)) + 1

            transform["region_id"] = rule.to_region
            state["last_transition_tick"] = result_tick
            state["generation"] = generation
            entity["version"] = result_version

            trace_seed = f"{agent_id}|{rule.rule_id}|{result_tick}|{rule.trace_address}"
            trace_id = "env_trace_" + sha256(trace_seed.encode("utf-8")).hexdigest()[:16]
            trace_value = {
                "entity_id": trace_id,
                "class": "environment_trace",
                "type": "environmental_effect",
                "status": "active",
                "version": result_version,
                "created_at_tick": result_tick,
                "components": {
                    "address": {"value": rule.trace_address},
                    "transform": {"region_id": rule.from_region},
                    "origin": {
                        "agent_id": agent_id,
                        "rule_id": rule.rule_id,
                        "generation": generation,
                    },
                },
            }
            updated.setdefault("entities", {})[trace_id] = trace_value

            operations.extend(
                [
                    {
                        "op": "set",
                        "path": f"/entities/{agent_id}/components/transform/region_id",
                        "value": rule.to_region,
                    },
                    {
                        "op": "set",
                        "path": f"/entities/{agent_id}/components/environmental_state",
                        "value": deepcopy(state),
                    },
                    {
                        "op": "add",
                        "path": f"/entities/{trace_id}",
                        "value": deepcopy(trace_value),
                    },
                ]
            )
            transitions.append(
                {
                    "agent_id": agent_id,
                    "rule_id": rule.rule_id,
                    "from_region": rule.from_region,
                    "to_region": rule.to_region,
                    "trace_id": trace_id,
                    "trace_address": rule.trace_address,
                    "generation": generation,
                }
            )

        delta_id = f"delta_{result_version:08d}"
        event_id = f"event_{result_tick:08d}_environment"
        delta = {
            "delta_id": delta_id,
            "base_version": before_version,
            "result_version": result_version,
            "tick_id": result_tick,
            "operations": deepcopy(operations),
            "provenance": {"origin": "environmental-agent-runtime"},
        }
        event = {
            "event_id": event_id,
            "tick_id": result_tick,
            "type": "environmental_tick",
            "actor": None,
            "targets": [item["agent_id"] for item in transitions],
            "before": {"version": before_version, "tick": before_tick},
            "after": {
                "version": result_version,
                "tick": result_tick,
                "transition_count": len(transitions),
            },
            "transitions": deepcopy(transitions),
            "delta_id": delta_id,
            "provenance": {
                "origin": "environmental-agent-runtime",
                "processed_by": "environmental-agent-runtime",
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
            EnvironmentalTick(
                world=deepcopy(updated),
                event=event,
                delta=delta,
                transitions=tuple(deepcopy(transitions)),
            )
        )

    return tuple(results)


@dataclass(frozen=True, slots=True)
class ReactiveEnvironmentalRule:
    rule_id: str
    agent_id: str
    min_ticks: int
    selectors: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ReactiveEnvironmentalTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    transitions: tuple[dict[str, Any], ...]


def _reactive_rules(
    world: dict[str, Any],
    agent_id: str,
) -> tuple[ReactiveEnvironmentalRule, ...]:
    parsed: list[ReactiveEnvironmentalRule] = []
    for raw in (world.get("rules") or {}).get("environmental_reactive_agents") or ():
        if str(raw.get("agent") or "") != agent_id:
            continue
        rule_id = str(raw.get("rule_id") or "")
        min_ticks = int(raw.get("min_ticks", 1))
        selectors_raw = raw.get("selectors") or ()
        selectors: list[tuple[str, str]] = []
        for selector in selectors_raw:
            property_id = str((selector or {}).get("property") or "")
            order = str((selector or {}).get("order") or "")
            if not property_id or order not in ("asc", "desc"):
                raise ValueError("reactive selector requires property and asc/desc order")
            selectors.append((property_id, order))
        if not rule_id or min_ticks < 1 or not selectors:
            continue
        parsed.append(
            ReactiveEnvironmentalRule(
                rule_id=rule_id,
                agent_id=agent_id,
                min_ticks=min_ticks,
                selectors=tuple(selectors),
            )
        )
    parsed.sort(key=lambda item: item.rule_id)
    return tuple(parsed)


def _reactive_routes(
    world: dict[str, Any],
    region_id: str,
    rule: ReactiveEnvironmentalRule,
) -> tuple[dict[str, Any], ...]:
    region = (world.get("regions") or {}).get(region_id) or {}
    routes = region.get("environmental_routes") or ()
    candidates: list[tuple[tuple[float | str, ...], dict[str, Any]]] = []

    for raw in routes:
        route_id = str((raw or {}).get("route_id") or "")
        to_region = str((raw or {}).get("to_region") or "")
        trace_address = str((raw or {}).get("trace_address") or "")
        if not route_id or not to_region or not trace_address:
            continue
        if raw.get("available", True) is False:
            continue

        properties = raw.get("properties") or {}
        key: list[float | str] = []
        valid = True
        for property_id, order in rule.selectors:
            if property_id not in properties:
                valid = False
                break
            value = properties[property_id]
            if not isinstance(value, (int, float)):
                raise ValueError("reactive route selector properties must be numeric")
            numeric = float(value)
            key.append(-numeric if order == "desc" else numeric)
        if not valid:
            continue

        # Stable route_id is the final deterministic tie-breaker.
        key.append(route_id)
        candidates.append((tuple(key), deepcopy(raw)))

    candidates.sort(key=lambda item: item[0])
    return tuple(item[1] for item in candidates)


def _ready_reactive_choice(
    world: dict[str, Any],
    agent_id: str,
    *,
    candidate_tick: int,
) -> tuple[ReactiveEnvironmentalRule, dict[str, Any]] | None:
    entity = (world.get("entities") or {}).get(agent_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        return None

    region_id = _region(entity)
    if region_id is None:
        return None

    state = ((entity.get("components") or {}).get("environmental_state") or {})
    last_tick = int(state.get("last_transition_tick", entity.get("created_at_tick", 0) or 0))

    for rule in _reactive_rules(world, agent_id):
        if candidate_tick - last_tick < rule.min_ticks:
            continue
        routes = _reactive_routes(world, region_id, rule)
        if routes:
            return rule, routes[0]
    return None


def advance_reactive_environmental_agents(
    world: dict[str, Any],
    *,
    ticks: int = 1,
) -> tuple[ReactiveEnvironmentalTick, ...]:
    """Advance environmental agents by world-declared local route properties.

    The runtime is property-name agnostic. It applies only the selector ordering
    declared in World State and never contains water-specific semantics.
    """
    if ticks < 1:
        raise ValueError("ticks must be >= 1")

    current = deepcopy(world)
    results: list[ReactiveEnvironmentalTick] = []

    for _ in range(ticks):
        before_version = int(current.get("current_version", 0))
        before_tick = int(current.get("current_tick", 0))
        result_version = before_version + 1
        result_tick = before_tick + 1

        updated = deepcopy(current)
        operations: list[dict[str, Any]] = []
        transitions: list[dict[str, Any]] = []

        for agent_id in environmental_agent_ids(current):
            choice = _ready_reactive_choice(current, agent_id, candidate_tick=result_tick)
            if choice is None:
                continue
            rule, route = choice

            entity = updated["entities"][agent_id]
            components = entity.setdefault("components", {})
            transform = components.setdefault("transform", {})
            state = components.setdefault("environmental_state", {})
            from_region = str(transform.get("region_id") or "")
            to_region = str(route["to_region"])
            generation = int(state.get("generation", 0)) + 1

            transform["region_id"] = to_region
            state["last_transition_tick"] = result_tick
            state["generation"] = generation
            state["last_route_id"] = str(route["route_id"])
            entity["version"] = result_version

            trace_seed = (
                f"{agent_id}|{rule.rule_id}|{route['route_id']}|"
                f"{result_tick}|{route['trace_address']}"
            )
            trace_id = "env_trace_" + sha256(trace_seed.encode("utf-8")).hexdigest()[:16]
            trace_value = {
                "entity_id": trace_id,
                "class": "environment_trace",
                "type": "environmental_effect",
                "status": "active",
                "version": result_version,
                "created_at_tick": result_tick,
                "components": {
                    "address": {"value": str(route["trace_address"])},
                    "transform": {"region_id": from_region},
                    "origin": {
                        "agent_id": agent_id,
                        "rule_id": rule.rule_id,
                        "route_id": str(route["route_id"]),
                        "generation": generation,
                    },
                    "route_properties": deepcopy(route.get("properties") or {}),
                },
            }
            updated.setdefault("entities", {})[trace_id] = trace_value

            operations.extend(
                [
                    {
                        "op": "set",
                        "path": f"/entities/{agent_id}/components/transform/region_id",
                        "value": to_region,
                    },
                    {
                        "op": "set",
                        "path": f"/entities/{agent_id}/components/environmental_state",
                        "value": deepcopy(state),
                    },
                    {
                        "op": "add",
                        "path": f"/entities/{trace_id}",
                        "value": deepcopy(trace_value),
                    },
                ]
            )
            transitions.append(
                {
                    "agent_id": agent_id,
                    "rule_id": rule.rule_id,
                    "route_id": str(route["route_id"]),
                    "from_region": from_region,
                    "to_region": to_region,
                    "trace_id": trace_id,
                    "trace_address": str(route["trace_address"]),
                    "route_properties": deepcopy(route.get("properties") or {}),
                    "generation": generation,
                }
            )

        delta_id = f"delta_{result_version:08d}"
        event_id = f"event_{result_tick:08d}_environment_reactive"
        delta = {
            "delta_id": delta_id,
            "base_version": before_version,
            "result_version": result_version,
            "tick_id": result_tick,
            "operations": deepcopy(operations),
            "provenance": {"origin": "environmental-reactive-runtime"},
        }
        event = {
            "event_id": event_id,
            "tick_id": result_tick,
            "type": "environmental_reactive_tick",
            "actor": None,
            "targets": [item["agent_id"] for item in transitions],
            "before": {"version": before_version, "tick": before_tick},
            "after": {
                "version": result_version,
                "tick": result_tick,
                "transition_count": len(transitions),
            },
            "transitions": deepcopy(transitions),
            "delta_id": delta_id,
            "provenance": {
                "origin": "environmental-reactive-runtime",
                "processed_by": "environmental-reactive-runtime",
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
            ReactiveEnvironmentalTick(
                world=deepcopy(updated),
                event=event,
                delta=delta,
                transitions=tuple(deepcopy(transitions)),
            )
        )

    return tuple(results)
