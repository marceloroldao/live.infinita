from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class RuntimeActionRule:
    rule_id: str
    action: str
    target: str | None
    possible_consequence_addresses: tuple[str, ...]
    consequence_address: str


@dataclass(frozen=True, slots=True)
class RuntimeExecution:
    proposal: dict[str, Any]
    delta: dict[str, Any]
    event: dict[str, Any]
    world: dict[str, Any]
    consequence_address: str


def _rules(world: dict[str, Any], actor_id: str) -> tuple[RuntimeActionRule, ...]:
    rules = (world.get("rules") or {}).get("actions") or ()
    parsed: list[RuntimeActionRule] = []
    for raw in rules:
        if raw.get("actor") not in (None, actor_id):
            continue
        rule_id = str(raw.get("rule_id") or "")
        action = str(raw.get("action") or "")
        consequence = str(raw.get("consequence_address") or "")
        possible = tuple(
            str(item)
            for item in (raw.get("possible_consequence_addresses") or (consequence,))
            if str(item)
        )
        target = raw.get("target")
        if not rule_id or not action or not consequence or not possible or consequence not in possible:
            continue
        parsed.append(RuntimeActionRule(rule_id, action, target, possible, consequence))
    parsed.sort(key=lambda item: item.rule_id)
    return tuple(parsed)


def generate_valid_actions(world: dict[str, Any], actor_id: str) -> tuple[dict[str, Any], ...]:
    entities = world.get("entities") or {}
    actor = entities.get(actor_id)
    if not isinstance(actor, dict) or actor.get("status") != "active":
        return ()

    tick = int(world.get("current_tick", 0))
    proposals: list[dict[str, Any]] = []
    for rule in _rules(world, actor_id):
        digest = sha256(f"{tick}|{actor_id}|{rule.rule_id}".encode("utf-8")).hexdigest()[:20]
        proposals.append(
            {
                "proposal_id": f"p_{digest}",
                "actor": actor_id,
                "action": rule.action,
                "target": rule.target,
                "parameters": {"rule_id": rule.rule_id},
                "source": "world-runtime",
                "reason": "world-rule-enabled",
                "tick_id": tick,
                "confidence": 1.0,
            }
        )
    return tuple(proposals)


def _rule_for_proposal(world: dict[str, Any], proposal: dict[str, Any]) -> RuntimeActionRule:
    actor_id = str(proposal.get("actor") or "")
    rule_id = str((proposal.get("parameters") or {}).get("rule_id") or "")
    current_tick = int(world.get("current_tick", 0))
    if int(proposal.get("tick_id", -1)) != current_tick:
        raise ValueError("proposal tick does not match current world tick")
    for rule in _rules(world, actor_id):
        if rule.rule_id == rule_id and rule.action == proposal.get("action") and rule.target == proposal.get("target"):
            return rule
    raise ValueError("proposal is not valid for the current world state")


def possible_action_outcomes(world: dict[str, Any], proposal: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    rule = _rule_for_proposal(world, proposal)
    return tuple((address,) for address in rule.possible_consequence_addresses)


def simulate_action_outcome(world: dict[str, Any], proposal: dict[str, Any]) -> tuple[str, ...]:
    rule = _rule_for_proposal(world, proposal)
    return (rule.consequence_address,)


def _active_runtime_observation_relations(world: dict[str, Any], actor_id: str) -> tuple[str, ...]:
    relation_ids: list[str] = []
    for relation_id, relation in (world.get("relations") or {}).items():
        source = (relation or {}).get("source") or {}
        if (
            relation.get("status") == "active"
            and relation.get("subject") == actor_id
            and source.get("type") == "world-runtime"
        ):
            relation_ids.append(str(relation_id))
    return tuple(sorted(relation_ids))


def pre_action_cognitive_world(world: dict[str, Any], actor_id: str) -> dict[str, Any]:
    """Return a non-authoritative pre-action projection for the next cognition step.

    The authoritative World State retains the most recent runtime observation and its
    complete Event/Delta history.  For the next prediction only, observation relations
    produced by the previous action are hidden so a transient sensory result does not
    become part of the situated context identity for the next action.

    This function never changes tick/version, never deletes history and never mutates
    the supplied world object.
    """
    projected = deepcopy(world)
    relations = projected.get("relations") or {}
    for relation_id in _active_runtime_observation_relations(world, actor_id):
        relation = relations.get(relation_id)
        if isinstance(relation, dict):
            relation["status"] = "inactive"
    return projected


def execute_validated_action(world: dict[str, Any], proposal: dict[str, Any]) -> RuntimeExecution:
    rule = _rule_for_proposal(world, proposal)
    before_version = int(world.get("current_version", 0))
    tick = int(world.get("current_tick", 0))
    result_version = before_version + 1
    result_tick = tick + 1

    effect_id = "effect_" + sha256(rule.consequence_address.encode("utf-8")).hexdigest()[:16]
    relation_id = "rel_" + sha256(f"{proposal['actor']}|{effect_id}".encode("utf-8")).hexdigest()[:16]
    delta_id = f"delta_{result_version:08d}"
    event_id = f"event_{result_tick:08d}_{proposal['proposal_id']}"

    operations: list[dict[str, Any]] = []
    for prior_relation_id in _active_runtime_observation_relations(world, proposal["actor"]):
        if prior_relation_id == relation_id:
            continue
        operations.append({"op": "deactivate", "path": f"/relations/{prior_relation_id}"})

    operations.extend(
        [
            {
                "op": "add",
                "path": f"/entities/{effect_id}",
                "value": {
                    "entity_id": effect_id,
                    "class": "observation",
                    "type": "runtime_effect",
                    "status": "active",
                    "version": result_version,
                    "created_at_tick": result_tick,
                    "components": {"address": {"value": rule.consequence_address}},
                },
            },
            {
                "op": "link",
                "path": f"/relations/{relation_id}",
                "value": {
                    "relation_id": relation_id,
                    "subject": proposal["actor"],
                    "predicate": "observes",
                    "object": effect_id,
                    "status": "active",
                    "confidence": 1.0,
                    "valid_from_tick": result_tick,
                    "valid_until_tick": None,
                    "source": {"type": "world-runtime", "proposal_id": proposal["proposal_id"]},
                    "version": result_version,
                },
            },
        ]
    )

    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": deepcopy(operations),
        "provenance": {"origin": "world-runtime", "proposal_id": proposal["proposal_id"]},
    }

    event = {
        "event_id": event_id,
        "tick_id": result_tick,
        "type": "action_committed",
        "actor": proposal["actor"],
        "targets": [proposal["target"]] if proposal.get("target") is not None else [],
        "cause": {"proposal_id": proposal["proposal_id"], "rule_id": rule.rule_id},
        "action": proposal["action"],
        "before": {"version": before_version, "tick": tick},
        "after": {"version": result_version, "tick": result_tick, "consequence_address": rule.consequence_address},
        "delta_id": delta_id,
        "provenance": {
            "origin": "world-runtime",
            "source_id": proposal["proposal_id"],
            "processed_by": "world-runtime",
            "validated_by": "world-runtime",
            "confidence": 1.0,
        },
    }

    updated = deepcopy(world)
    relations = updated.setdefault("relations", {})
    for prior_relation_id in _active_runtime_observation_relations(world, proposal["actor"]):
        if prior_relation_id == relation_id:
            continue
        if prior_relation_id in relations:
            relations[prior_relation_id]["status"] = "inactive"
            relations[prior_relation_id]["valid_until_tick"] = result_tick
            relations[prior_relation_id]["version"] = result_version

    effect_value = deepcopy(next(item["value"] for item in operations if item["op"] == "add"))
    relation_value = deepcopy(next(item["value"] for item in operations if item["op"] == "link"))
    updated.setdefault("entities", {})[effect_id] = effect_value
    relations[relation_id] = relation_value
    updated.setdefault("deltas", {})[delta_id] = deepcopy(delta)
    updated.setdefault("events", {})[event_id] = deepcopy(event)
    updated.setdefault("versions", {})[str(result_version)] = {
        "parent_version": before_version,
        "delta_id": delta_id,
    }
    updated["current_version"] = result_version
    updated["current_tick"] = result_tick

    return RuntimeExecution(
        proposal=deepcopy(proposal),
        delta=delta,
        event=event,
        world=updated,
        consequence_address=rule.consequence_address,
    )


def offered_outcomes(world: dict[str, Any], proposals: Iterable[dict[str, Any]]) -> dict[str, tuple[tuple[str, ...], ...]]:
    return {proposal["proposal_id"]: possible_action_outcomes(world, proposal) for proposal in proposals}
