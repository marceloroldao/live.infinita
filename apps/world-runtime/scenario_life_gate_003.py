from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_002 import build_life_gate_002_world


def build_life_gate_003_world() -> dict:
    """Replace the static source with the first persistent environmental agent."""
    world = deepcopy(build_life_gate_002_world())
    world["world_id"] = "life-gate-003"

    world["entities"].pop("source_alpha", None)
    for relation_id in tuple(world.get("relations", {})):
        relation = world["relations"][relation_id]
        if relation.get("object") == "source_alpha" or relation.get("subject") == "source_alpha":
            del world["relations"][relation_id]

    world["entities"]["water_01"] = {
        "entity_id": "water_01",
        "class": "environmental_agent",
        "type": "water",
        "status": "active",
        "version": int(world["current_version"]),
        "created_at_tick": int(world["current_tick"]),
        "components": {
            "transform": {"region_id": "spring"},
            "environmental_state": {
                "last_transition_tick": int(world["current_tick"]),
                "generation": 0,
            },
        },
    }
    world["entities"]["nova"]["components"]["transform"]["region_id"] = "spring"

    for rule in world["rules"]["actions"]:
        if rule["rule_id"] == "probe_source":
            rule["rule_id"] = "probe_water"
            rule["target"] = "water_01"
            rule["possible_consequence_addresses"] = [
                "live:effect:aqueous-alpha",
                "live:effect:aqueous-beta",
            ]
            rule["consequence_address"] = "live:effect:aqueous-alpha"
            rule["requires_target_colocation"] = True

    world["rules"]["environmental_agents"] = [
        {
            "rule_id": "water_spring_to_stream",
            "agent": "water_01",
            "from_region": "spring",
            "to_region": "stream",
            "min_ticks": 4,
            "trace_address": "live:environment:trace:wet-spring",
        },
        {
            "rule_id": "water_stream_to_basin",
            "agent": "water_01",
            "from_region": "stream",
            "to_region": "basin",
            "min_ticks": 2,
            "trace_address": "live:environment:trace:wet-stream",
        },
        {
            "rule_id": "water_basin_to_spring",
            "agent": "water_01",
            "from_region": "basin",
            "to_region": "spring",
            "min_ticks": 3,
            "trace_address": "live:environment:trace:wet-basin",
        },
    ]
    return world


def initial_nov_needs_003(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
