from __future__ import annotations

from copy import deepcopy
from hashlib import sha256


SOURCE_RELATION_ID = "rel_nova_source_alpha"


def build_life_gate_world() -> dict:
    """Create the minimal persistent world used by Life Gate 001.

    The Live runtime owns only observable state, available actions and concrete
    consequences. No cognitive meaning is embedded in the Memoria.ia core.
    """
    return {
        "world_id": "life-gate-001",
        "current_tick": 100,
        "current_version": 100,
        "entities": {
            "nova": {
                "entity_id": "nova",
                "status": "active",
                "components": {"transform": {"region_id": "forest_source_edge"}},
            },
            "source_alpha": {
                "entity_id": "source_alpha",
                "status": "active",
                "components": {"transform": {"region_id": "forest_source_edge"}},
            },
        },
        "relations": {
            SOURCE_RELATION_ID: {
                "relation_id": SOURCE_RELATION_ID,
                "subject": "nova",
                "predicate": "near",
                "object": "source_alpha",
                "status": "active",
                "confidence": 1.0,
                "valid_from_tick": 100,
                "valid_until_tick": None,
                "source": {"type": "world-fixture"},
                "version": 100,
            }
        },
        "rules": {
            "actions": [
                {
                    "rule_id": "probe_source",
                    "actor": "nova",
                    "action": "probe",
                    "target": "source_alpha",
                    "possible_consequence_addresses": [
                        "live:effect:alpha",
                        "live:effect:beta",
                    ],
                    "consequence_address": "live:effect:alpha",
                },
                {
                    "rule_id": "continue_path",
                    "actor": "nova",
                    "action": "continue",
                    "target": None,
                    "possible_consequence_addresses": [
                        "live:outcome:no-structural-change"
                    ],
                    "consequence_address": "live:outcome:no-structural-change",
                },
            ]
        },
        "events": {},
        "deltas": {},
        "versions": {"100": {"parent_version": 99, "delta_id": None}},
    }


def _transition_id(kind: str, tick: int, value: str) -> str:
    digest = sha256(f"{kind}|{tick}|{value}".encode("utf-8")).hexdigest()[:16]
    return digest


def relocate_nova(world: dict, region_id: str, *, near_source: bool) -> dict:
    """Apply a world-owned spatial transition and preserve deterministic history."""
    updated = deepcopy(world)
    before_version = int(world.get("current_version", 0))
    before_tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = before_tick + 1

    nova = updated["entities"]["nova"]
    nova.setdefault("components", {}).setdefault("transform", {})["region_id"] = region_id

    relation = updated["relations"][SOURCE_RELATION_ID]
    relation["status"] = "active" if near_source else "inactive"
    relation["version"] = result_version
    if near_source:
        relation["valid_from_tick"] = result_tick
        relation["valid_until_tick"] = None
    else:
        relation["valid_until_tick"] = result_tick

    transition = _transition_id("relocate", result_tick, f"{region_id}|{near_source}")
    delta_id = f"delta_{result_version:08d}_{transition}"
    event_id = f"event_{result_tick:08d}_{transition}"

    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": [
            {
                "op": "set",
                "path": "/entities/nova/components/transform/region_id",
                "value": region_id,
            },
            {
                "op": "set",
                "path": f"/relations/{SOURCE_RELATION_ID}/status",
                "value": relation["status"],
            },
        ],
        "provenance": {"origin": "world-runtime", "kind": "relocate"},
    }
    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "world_transition",
        "actor": "nova",
        "targets": [],
        "before": {"version": before_version, "tick": before_tick},
        "after": {
            "version": result_version,
            "tick": result_tick,
            "region_id": region_id,
            "near_source": near_source,
        },
        "delta_id": delta_id,
        "provenance": {"origin": "world-runtime", "kind": "relocate"},
    }

    updated.setdefault("deltas", {})[delta_id] = delta
    updated.setdefault("events", {})[event_id] = event
    updated.setdefault("versions", {})[str(result_version)] = {
        "parent_version": before_version,
        "delta_id": delta_id,
    }
    updated["current_version"] = result_version
    updated["current_tick"] = result_tick
    return updated


def advance_ambient_ticks(world: dict, count: int) -> dict:
    """Advance unrelated world time without creating cognitive observations."""
    if count < 0:
        raise ValueError("count must be >= 0")

    updated = deepcopy(world)
    for _ in range(count):
        before_version = int(updated.get("current_version", 0))
        before_tick = int(updated.get("current_tick", 0))
        result_version = before_version + 1
        result_tick = before_tick + 1
        marker = _transition_id("ambient", result_tick, updated["entities"]["nova"]["components"]["transform"]["region_id"])
        delta_id = f"delta_{result_version:08d}_{marker}"
        event_id = f"event_{result_tick:08d}_{marker}"

        delta = {
            "delta_id": delta_id,
            "base_version": before_version,
            "result_version": result_version,
            "tick_id": result_tick,
            "operations": [],
            "provenance": {"origin": "world-runtime", "kind": "ambient"},
        }
        event = {
            "event_id": event_id,
            "tick_id": result_tick,
            "type": "ambient_tick",
            "actor": None,
            "targets": [],
            "before": {"version": before_version, "tick": before_tick},
            "after": {"version": result_version, "tick": result_tick},
            "delta_id": delta_id,
            "provenance": {"origin": "world-runtime", "kind": "ambient"},
        }

        updated.setdefault("deltas", {})[delta_id] = delta
        updated.setdefault("events", {})[event_id] = event
        updated.setdefault("versions", {})[str(result_version)] = {
            "parent_version": before_version,
            "delta_id": delta_id,
        }
        updated["current_version"] = result_version
        updated["current_tick"] = result_tick
    return updated
