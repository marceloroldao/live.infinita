from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class EnvironmentalInfluencePhase:
    phase_id: str
    action_id: str
    next_phase_id: str
    route_overrides: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class EnvironmentalInfluenceRule:
    rule_id: str
    agent_id: str
    min_ticks: int
    phases: tuple[EnvironmentalInfluencePhase, ...]


@dataclass(frozen=True, slots=True)
class EnvironmentalInfluenceTick:
    world: dict[str, Any]
    event: dict[str, Any]
    delta: dict[str, Any]
    influences: tuple[dict[str, Any], ...]


def _agent_ids(world: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
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
) -> tuple[EnvironmentalInfluenceRule, ...]:
    parsed: list[EnvironmentalInfluenceRule] = []
    for raw in (world.get("rules") or {}).get("environmental_influence_agents") or ():
        if str((raw or {}).get("agent") or "") != agent_id:
            continue
        rule_id = str((raw or {}).get("rule_id") or "")
        min_ticks = int((raw or {}).get("min_ticks", 1))
        if not rule_id or min_ticks < 1:
            continue

        phases: list[EnvironmentalInfluencePhase] = []
        seen: set[str] = set()
        for phase in (raw or {}).get("phases") or ():
            phase_id = str((phase or {}).get("phase_id") or "")
            action_id = str((phase or {}).get("action_id") or "")
            next_phase_id = str((phase or {}).get("next_phase_id") or "")
            if (
                not phase_id
                or phase_id in seen
                or not action_id
                or not next_phase_id
            ):
                raise ValueError("influence phases require unique phase/action/next IDs")
            seen.add(phase_id)

            overrides: list[dict[str, Any]] = []
            for override in (phase or {}).get("route_overrides") or ():
                region_id = str((override or {}).get("region_id") or "")
                route_id = str((override or {}).get("route_id") or "")
                available = (override or {}).get("available")
                if not region_id or not route_id or not isinstance(available, bool):
                    raise ValueError(
                        "influence route override requires region_id, route_id and bool available"
                    )
                overrides.append(
                    {
                        "region_id": region_id,
                        "route_id": route_id,
                        "available": available,
                    }
                )
            if not overrides:
                raise ValueError("influence phase requires at least one route override")
            phases.append(
                EnvironmentalInfluencePhase(
                    phase_id=phase_id,
                    action_id=action_id,
                    next_phase_id=next_phase_id,
                    route_overrides=tuple(overrides),
                )
            )

        phase_ids = {item.phase_id for item in phases}
        if not phases or any(item.next_phase_id not in phase_ids for item in phases):
            raise ValueError("influence phase graph must be closed")
        phases.sort(key=lambda item: item.phase_id)
        parsed.append(
            EnvironmentalInfluenceRule(
                rule_id=rule_id,
                agent_id=agent_id,
                min_ticks=min_ticks,
                phases=tuple(phases),
            )
        )

    parsed.sort(key=lambda item: item.rule_id)
    return tuple(parsed)


def _current_phase(entity: dict[str, Any]) -> str:
    state = ((entity.get("components") or {}).get("environmental_state") or {})
    phase_id = str(state.get("phase_id") or "")
    if not phase_id:
        raise ValueError("influence environmental agent requires environmental_state.phase_id")
    return phase_id


def _apply_route_overrides(
    world: dict[str, Any],
    overrides: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    operations: list[dict[str, Any]] = []
    for override in overrides:
        region = (world.get("regions") or {}).get(override["region_id"])
        if not isinstance(region, dict):
            raise ValueError("influence override references missing region")
        routes = region.get("environmental_routes") or ()
        route_index = None
        for index, route in enumerate(routes):
            if str((route or {}).get("route_id") or "") == override["route_id"]:
                route["available"] = override["available"]
                route_index = index
                break
        if route_index is None:
            raise ValueError("influence override references missing route")
        operations.append(
            {
                "op": "set",
                "path": (
                    f"/regions/{override['region_id']}/environmental_routes/"
                    f"{route_index}/available"
                ),
                "value": override["available"],
            }
        )
    return tuple(operations)


def advance_environmental_influence_agents(
    world: dict[str, Any],
    *,
    ticks: int = 1,
) -> tuple[EnvironmentalInfluenceTick, ...]:
    """Advance autonomous environmental influence agents by their own phase graph.

    The active phase selects the agent action. The action mutates only world-declared
    physical route properties, then the agent advances to its next phase. No observer,
    Memoria.ia state, or external branch selection participates in this transition.
    """
    if ticks < 1:
        raise ValueError("ticks must be >= 1")

    current = deepcopy(world)
    results: list[EnvironmentalInfluenceTick] = []

    for _ in range(ticks):
        before_version = int(current.get("current_version", 0))
        before_tick = int(current.get("current_tick", 0))
        result_version = before_version + 1
        result_tick = before_tick + 1
        updated = deepcopy(current)
        operations: list[dict[str, Any]] = []
        influences: list[dict[str, Any]] = []

        for agent_id in _agent_ids(current):
            entity_before = current["entities"][agent_id]
            state_before = (
                (entity_before.get("components") or {}).get("environmental_state") or {}
            )
            last_tick = int(
                state_before.get(
                    "last_transition_tick",
                    entity_before.get("created_at_tick", 0) or 0,
                )
            )
            matching = _rules(current, agent_id)
            if not matching:
                continue
            rule = matching[0]
            if result_tick - last_tick < rule.min_ticks:
                continue

            phase_id = _current_phase(entity_before)
            phases = {item.phase_id: item for item in rule.phases}
            phase = phases.get(phase_id)
            if phase is None:
                raise ValueError("agent phase is not declared by influence rule")

            override_operations = _apply_route_overrides(
                updated,
                phase.route_overrides,
            )
            operations.extend(deepcopy(override_operations))

            entity = updated["entities"][agent_id]
            components = entity.setdefault("components", {})
            state = components.setdefault("environmental_state", {})
            generation = int(state.get("generation", 0)) + 1
            state["phase_id"] = phase.next_phase_id
            state["last_action_id"] = phase.action_id
            state["last_transition_tick"] = result_tick
            state["generation"] = generation
            entity["version"] = result_version

            operations.append(
                {
                    "op": "set",
                    "path": f"/entities/{agent_id}/components/environmental_state",
                    "value": deepcopy(state),
                }
            )

            trace_seed = "|".join(
                (
                    agent_id,
                    rule.rule_id,
                    phase.phase_id,
                    phase.action_id,
                    phase.next_phase_id,
                    str(result_tick),
                )
            )
            trace_id = "influence_trace_" + sha256(
                trace_seed.encode("utf-8")
            ).hexdigest()[:16]
            trace = {
                "entity_id": trace_id,
                "class": "environment_trace",
                "type": "environmental_influence",
                "status": "active",
                "version": result_version,
                "created_at_tick": result_tick,
                "components": {
                    "transform": deepcopy(
                        (entity.get("components") or {}).get("transform") or {}
                    ),
                    "origin": {
                        "agent_id": agent_id,
                        "rule_id": rule.rule_id,
                        "phase_id": phase.phase_id,
                        "action_id": phase.action_id,
                        "next_phase_id": phase.next_phase_id,
                        "generation": generation,
                    },
                    "route_overrides": tuple(deepcopy(phase.route_overrides)),
                },
            }
            updated.setdefault("entities", {})[trace_id] = trace
            operations.append(
                {
                    "op": "add",
                    "path": f"/entities/{trace_id}",
                    "value": deepcopy(trace),
                }
            )
            influences.append(
                {
                    "agent_id": agent_id,
                    "rule_id": rule.rule_id,
                    "phase_id": phase.phase_id,
                    "action_id": phase.action_id,
                    "next_phase_id": phase.next_phase_id,
                    "route_overrides": tuple(deepcopy(phase.route_overrides)),
                    "trace_id": trace_id,
                    "generation": generation,
                }
            )

        delta_id = f"delta_{result_version:08d}"
        event_id = f"event_{result_tick:08d}_environment_influence"
        delta = {
            "delta_id": delta_id,
            "base_version": before_version,
            "result_version": result_version,
            "tick_id": result_tick,
            "operations": deepcopy(operations),
            "provenance": {"origin": "environmental-influence-agent-runtime"},
        }
        event = {
            "event_id": event_id,
            "tick_id": result_tick,
            "type": "environmental_influence_tick",
            "actor": influences[0]["agent_id"] if len(influences) == 1 else None,
            "targets": [item["agent_id"] for item in influences],
            "before": {"version": before_version, "tick": before_tick},
            "after": {
                "version": result_version,
                "tick": result_tick,
                "influence_count": len(influences),
            },
            "influences": deepcopy(influences),
            "delta_id": delta_id,
            "provenance": {
                "origin": "environmental-influence-agent-runtime",
                "processed_by": "environmental-influence-agent-runtime",
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
            EnvironmentalInfluenceTick(
                world=deepcopy(updated),
                event=event,
                delta=delta,
                influences=tuple(deepcopy(influences)),
            )
        )

    return tuple(results)
