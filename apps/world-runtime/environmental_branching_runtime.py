from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame


@dataclass(frozen=True, slots=True)
class EnvironmentalBranchState:
    control_id: str
    state_id: str
    entity_id: str
    route_overrides: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class BranchingSensorFutureCandidate:
    candidate_id: str
    branch_id: str
    control_id: str
    control_state_id: str
    observer_id: str
    sensor_id: str
    band_id: str
    target_id: str
    region_id: str
    source_tick: int
    source_version: int
    physical_tick: int
    sensor_tick: int
    physical_event_id: str
    sensor_frame_id: str


@dataclass(frozen=True, slots=True)
class BranchingSensorFutureSet:
    observer_id: str
    source_tick: int
    source_version: int
    control_id: str
    candidates: tuple[BranchingSensorFutureCandidate, ...]


@dataclass(frozen=True, slots=True)
class EnvironmentalBranchCommit:
    world: dict[str, Any]
    branch_id: str
    control_id: str
    control_state_id: str
    physical_event_id: str
    sensor_frame_id: str


def _branching_rule(world: dict[str, Any]) -> dict[str, Any]:
    rule = (world.get("rules") or {}).get("environmental_branching_control") or {}
    control_id = str(rule.get("control_id") or "")
    entity_id = str(rule.get("entity_id") or "")
    runtime = str(rule.get("runtime") or "")
    lookahead_ticks = int(rule.get("lookahead_ticks", 0))
    states = tuple(rule.get("admissible_next_states") or ())
    if not control_id or not entity_id:
        raise ValueError("branching control requires control_id and entity_id")
    if runtime != "distributed_environmental":
        raise ValueError("branching control runtime must be distributed_environmental")
    if lookahead_ticks != 1:
        raise ValueError("Life Gate 013 supports exactly one branching lookahead tick")
    if len(states) < 2:
        raise ValueError("branching control requires at least two admissible next states")
    return rule


def _parse_states(world: dict[str, Any]) -> tuple[EnvironmentalBranchState, ...]:
    rule = _branching_rule(world)
    control_id = str(rule["control_id"])
    entity_id = str(rule["entity_id"])
    entity = (world.get("entities") or {}).get(entity_id)
    if not isinstance(entity, dict) or entity.get("status") != "active":
        raise ValueError("branching control entity must exist and be active")

    states: list[EnvironmentalBranchState] = []
    seen: set[str] = set()
    for raw in rule.get("admissible_next_states") or ():
        state_id = str((raw or {}).get("state_id") or "")
        if not state_id or state_id in seen:
            raise ValueError("branching control state IDs must be unique and non-empty")
        seen.add(state_id)
        overrides = []
        for override in (raw or {}).get("route_overrides") or ():
            region_id = str((override or {}).get("region_id") or "")
            route_id = str((override or {}).get("route_id") or "")
            available = (override or {}).get("available")
            if not region_id or not route_id or not isinstance(available, bool):
                raise ValueError("route override requires region_id, route_id and bool available")
            overrides.append(
                {
                    "region_id": region_id,
                    "route_id": route_id,
                    "available": available,
                }
            )
        if not overrides:
            raise ValueError("branching control state requires at least one route override")
        states.append(
            EnvironmentalBranchState(
                control_id=control_id,
                state_id=state_id,
                entity_id=entity_id,
                route_overrides=tuple(overrides),
            )
        )
    states.sort(key=lambda item: item.state_id)
    return tuple(states)


def _apply_branch_state(
    world: dict[str, Any],
    branch: EnvironmentalBranchState,
) -> dict[str, Any]:
    updated = deepcopy(world)
    entity = updated["entities"][branch.entity_id]
    control = entity.setdefault("components", {}).setdefault("environmental_control", {})
    control["control_id"] = branch.control_id
    control["state_id"] = branch.state_id

    for override in branch.route_overrides:
        region = (updated.get("regions") or {}).get(override["region_id"])
        if not isinstance(region, dict):
            raise ValueError("branch route override references missing region")
        found = False
        for route in region.get("environmental_routes") or ():
            if str((route or {}).get("route_id") or "") == override["route_id"]:
                route["available"] = override["available"]
                found = True
                break
        if not found:
            raise ValueError("branch route override references missing route")
    return updated


def _branch_id(world: dict[str, Any], branch: EnvironmentalBranchState) -> str:
    seed = "|".join(
        (
            str(world.get("world_id") or ""),
            branch.control_id,
            branch.state_id,
            str(world.get("current_version", 0)),
            str(world.get("current_tick", 0)),
        )
    )
    return "physical_branch_" + sha256(seed.encode("utf-8")).hexdigest()[:20]


def enumerate_branching_distributed_sensor_candidates(
    world: dict[str, Any],
    *,
    observer_id: str,
    sensor_ids: Iterable[str] | None = None,
) -> BranchingSensorFutureSet:
    """Enumerate all World-State-declared admissible external-control branches.

    Every branch is materialized on a copy, then advanced by the real distributed
    physics and sampled by the real multimodal sensor runtime. Memoria.ia is not used
    anywhere in branch creation.
    """
    rule = _branching_rule(world)
    source_tick = int(world.get("current_tick", 0))
    source_version = int(world.get("current_version", 0))
    requested = None
    if sensor_ids is not None:
        requested = {str(value) for value in sensor_ids}
        if not requested or "" in requested:
            raise ValueError("sensor_ids must contain non-empty values")

    candidates: list[BranchingSensorFutureCandidate] = []
    for branch in _parse_states(world):
        branched_world = _apply_branch_state(world, branch)
        physical = advance_distributed_environmental_agents(branched_world, ticks=1)[0]
        sensed = sample_multimodal_sensor_frame(
            physical.world,
            observer_id=observer_id,
        )
        branch_id = _branch_id(world, branch)

        for sample in sorted(sensed.samples, key=lambda item: item.sensor_id):
            if requested is not None and sample.sensor_id not in requested:
                continue
            seed = "|".join(
                (
                    branch_id,
                    observer_id,
                    sample.sensor_id,
                    sample.band_id,
                    physical.event["event_id"],
                    sensed.frame_id,
                )
            )
            candidate_id = "branch_future_" + sha256(seed.encode("utf-8")).hexdigest()[:24]
            candidates.append(
                BranchingSensorFutureCandidate(
                    candidate_id=candidate_id,
                    branch_id=branch_id,
                    control_id=branch.control_id,
                    control_state_id=branch.state_id,
                    observer_id=observer_id,
                    sensor_id=sample.sensor_id,
                    band_id=sample.band_id,
                    target_id=sample.target_id,
                    region_id=sample.region_id,
                    source_tick=source_tick,
                    source_version=source_version,
                    physical_tick=int(physical.event["tick_id"]),
                    sensor_tick=int(sensed.event["tick_id"]),
                    physical_event_id=str(physical.event["event_id"]),
                    sensor_frame_id=sensed.frame_id,
                )
            )

    if requested is not None:
        found = {item.sensor_id for item in candidates}
        missing = tuple(sorted(requested - found))
        if missing:
            raise ValueError(f"requested sensors not present in branching preview: {missing}")

    candidates.sort(
        key=lambda item: (
            item.control_state_id,
            item.sensor_id,
            item.band_id,
            item.candidate_id,
        )
    )
    return BranchingSensorFutureSet(
        observer_id=observer_id,
        source_tick=source_tick,
        source_version=source_version,
        control_id=str(rule["control_id"]),
        candidates=tuple(candidates),
    )


def commit_branching_environmental_state(
    world: dict[str, Any],
    *,
    observer_id: str,
    control_state_id: str,
) -> EnvironmentalBranchCommit:
    """Commit one externally selected physical branch.

    This function requires the external control state explicitly. It does not consult
    Memoria.ia or a prediction result to choose the branch.
    """
    branches = {item.state_id: item for item in _parse_states(world)}
    branch = branches.get(str(control_state_id))
    if branch is None:
        raise ValueError("control_state_id is not physically admissible")

    branched_world = _apply_branch_state(world, branch)
    physical = advance_distributed_environmental_agents(branched_world, ticks=1)[0]
    sensed = sample_multimodal_sensor_frame(
        physical.world,
        observer_id=observer_id,
    )
    return EnvironmentalBranchCommit(
        world=sensed.world,
        branch_id=_branch_id(world, branch),
        control_id=branch.control_id,
        control_state_id=branch.state_id,
        physical_event_id=str(physical.event["event_id"]),
        sensor_frame_id=sensed.frame_id,
    )
