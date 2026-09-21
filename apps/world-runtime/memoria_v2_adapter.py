from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any, Iterable


def _addr(namespace: str, value: str) -> str:
    if not value:
        raise ValueError(f"empty {namespace} address value")
    return f"live:{namespace}:{value}"


def _stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class CognitiveIntervention:
    intervention_address: str
    proposal_id: str


@dataclass(frozen=True, slots=True)
class CognitiveCandidate:
    candidate_id: str
    proposal_id: str
    consequence_addresses: tuple[str, ...]
    next_state_addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CognitiveFrame:
    frame_id: str
    tick_id: int
    observer_id: str
    state_addresses: tuple[str, ...]
    available_interventions: tuple[CognitiveIntervention, ...]
    candidate_outcomes: tuple[CognitiveCandidate, ...]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observer_state_addresses(world: dict[str, Any], observer_id: str) -> tuple[str, ...]:
    """Project a deterministic local structural view for one observer."""
    entities = world.get("entities") or {}
    observer = entities.get(observer_id)
    if not isinstance(observer, dict):
        raise ValueError(f"unknown observer_id: {observer_id}")

    values: list[str] = [_addr("entity", observer_id)]
    status = observer.get("status")
    if status:
        values.append(_addr("status", str(status)))

    transform = ((observer.get("components") or {}).get("transform") or {})
    region_id = transform.get("region_id")
    if region_id:
        values.append(_addr("region", str(region_id)))

    relations = world.get("relations") or {}
    for relation_id in sorted(relations):
        relation = relations[relation_id] or {}
        if relation.get("status") != "active":
            continue
        subject = relation.get("subject")
        obj = relation.get("object")
        if observer_id not in (subject, obj):
            continue
        values.append(_addr("relation", relation_id))
        if subject:
            values.append(_addr("entity", str(subject)))
        if obj:
            values.append(_addr("entity", str(obj)))

    return _stable_unique(values)


def intervention_from_proposal(proposal: dict[str, Any]) -> CognitiveIntervention:
    proposal_id = str(proposal.get("proposal_id") or "")
    actor = str(proposal.get("actor") or "")
    action = str(proposal.get("action") or "")
    target = proposal.get("target")
    if not proposal_id or not actor or not action:
        raise ValueError("proposal requires proposal_id, actor and action")

    raw = f"{actor}|{action}|{target if target is not None else ''}"
    digest = sha256(raw.encode("utf-8")).hexdigest()[:24]
    return CognitiveIntervention(
        intervention_address=_addr("intervention", digest),
        proposal_id=proposal_id,
    )


def candidate_from_transition(
    *,
    candidate_id: str,
    proposal_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
    observer_id: str,
    event_ids: Iterable[str] = (),
) -> CognitiveCandidate:
    if not candidate_id or not proposal_id:
        raise ValueError("candidate_id and proposal_id must be non-empty")
    before_state = observer_state_addresses(before, observer_id)
    after_state = observer_state_addresses(after, observer_id)

    before_set = set(before_state)
    consequences = tuple(item for item in after_state if item not in before_set)
    if not consequences:
        consequences = (_addr("outcome", "no-structural-change"),)

    return CognitiveCandidate(
        candidate_id=candidate_id,
        proposal_id=proposal_id,
        consequence_addresses=consequences,
        next_state_addresses=after_state,
    )


def build_cognitive_frame(
    *,
    world: dict[str, Any],
    observer_id: str,
    proposals: Iterable[dict[str, Any]],
    candidates: Iterable[CognitiveCandidate] = (),
    event_ids: Iterable[str] = (),
) -> CognitiveFrame:
    tick_id = int(world.get("current_tick", 0))
    version = world.get("current_version")
    state = observer_state_addresses(world, observer_id)

    interventions = tuple(
        sorted(
            (intervention_from_proposal(item) for item in proposals),
            key=lambda item: (item.intervention_address, item.proposal_id),
        )
    )
    proposal_ids = {item.proposal_id for item in interventions}
    if len(proposal_ids) != len(interventions):
        raise ValueError("proposal_id must be unique within a cognitive frame")

    candidate_tuple = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    if len({item.candidate_id for item in candidate_tuple}) != len(candidate_tuple):
        raise ValueError("candidate_id must be unique within a cognitive frame")
    if any(item.proposal_id not in proposal_ids for item in candidate_tuple):
        raise ValueError("every candidate must reference an available proposal_id")

    frame_seed = "|".join(
        [str(tick_id), observer_id, *state, *(item.proposal_id for item in interventions)]
    )
    frame_id = f"cf_{sha256(frame_seed.encode('utf-8')).hexdigest()[:24]}"

    return CognitiveFrame(
        frame_id=frame_id,
        tick_id=tick_id,
        observer_id=observer_id,
        state_addresses=state,
        available_interventions=interventions,
        candidate_outcomes=candidate_tuple,
        provenance={
            "world_version": version,
            "snapshot_id": None,
            "event_ids": tuple(sorted(set(event_ids))),
        },
    )


def to_memoria_v2_request_payload(frame: CognitiveFrame, *, proposal_id: str) -> dict[str, Any]:
    """Select exactly one Live intervention and emit Memoria.ia V2's request shape."""
    matches = tuple(item for item in frame.available_interventions if item.proposal_id == proposal_id)
    if len(matches) != 1:
        raise ValueError("proposal_id must identify exactly one available intervention")
    intervention = matches[0]
    candidates = tuple(item for item in frame.candidate_outcomes if item.proposal_id == proposal_id)

    return {
        "frame_id": frame.frame_id,
        "state_addresses": frame.state_addresses,
        "intervention_id": proposal_id,
        "intervention_address": intervention.intervention_address,
        "candidates": tuple(
            (
                item.candidate_id,
                item.consequence_addresses,
                item.next_state_addresses,
            )
            for item in candidates
        ),
        "provenance": "live.infinita",
    }
