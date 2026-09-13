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
        target = raw.get("target")
        if not rule_id or not action or not consequence:
            continue
        parsed.append(RuntimeActionRule(rule_id, action, target, consequence))
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


def simulate_action_outcome(world: dict[str, Any], proposal: dict[str, Any]) -> tuple[str, ...]:
    rule = _rule_for_proposal(world, proposal)
    return (rule.consequence_address,)


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

    operations = (
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
    )

    delta = {
        "delta_id": delta_id,
        "base_version": before_version,
        "result_version": result_version,
        "tick_id": result_tick,
        "operations": list(operations),
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
    updated.setdefault("entities", {})[effect_id] = deepcopy(operations[0]["value"])
    updated.setdefault("relations", {})[relation_id] = deepcopy(operations[1]["value"])
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


def offered_outcomes(world: dict[str, Any], proposals: Iterable[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    return {proposal["proposal_id"]: simulate_action_outcome(world, proposal) for proposal in proposals}
