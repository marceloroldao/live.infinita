from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Iterable


NOV_ACTION_TARGETS = {
    "nov_to_fire": "fire_01",
    "nov_to_shelter": "shelter_marker",
    "nov_to_forest": "ancient_tree",
}
NOV_ACTIONS = ("nov_to_fire", "nov_to_shelter", "nov_to_forest", "nov_explore")


def _addr(namespace: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"empty {namespace} address value")
    return f"live:{namespace}:{normalized}"


def _stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CognitiveIntervention:
    intervention_address: str
    proposal_id: str
    action: str
    target_entity_id: str


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


def observer_state_addresses(
    world: dict[str, Any],
    observer: dict[str, Any],
) -> tuple[str, ...]:
    observer_id = str(observer.get("id") or "").strip()
    if not observer_id:
        raise ValueError("observer entity requires id")

    values = [
        _addr("world", str(world.get("world_id") or "unknown")),
        _addr("entity", observer_id),
    ]
    entity_type = str(observer.get("type") or "").strip()
    if entity_type:
        values.append(_addr("type", entity_type))
    region_id = str(observer.get("region_id") or "").strip()
    if region_id:
        values.append(_addr("region", region_id))

    environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
    for namespace, key in (
        ("period", "period"),
        ("weather", "weather"),
        ("biome", "biome"),
    ):
        value = str(environment.get(key) or "").strip()
        if value:
            values.append(_addr(namespace, value))

    properties = observer.get("properties") if isinstance(observer.get("properties"), dict) else {}
    needs = properties.get("needs") if isinstance(properties.get("needs"), dict) else {}
    for name in sorted(needs):
        try:
            value = float(needs[name])
        except (TypeError, ValueError):
            continue
        bucket = "low" if value < 0.34 else "medium" if value < 0.67 else "high"
        values.append(_addr("need", f"{name}:{bucket}"))

    return _stable_unique(values)


def target_for_action(action: str, observer: dict[str, Any]) -> str:
    if action in NOV_ACTION_TARGETS:
        return NOV_ACTION_TARGETS[action]
    if action != "nov_explore":
        raise ValueError(f"unsupported cognitive action: {action}")
    region_id = str(observer.get("region_id") or "")
    return {
        "clearing": "ancient_tree",
        "deep_forest": "shelter_marker",
        "shelter": "fire_01",
    }.get(region_id, "ancient_tree")


def intervention_for_action(
    *,
    tick_id: int,
    observer_id: str,
    action: str,
    target_entity_id: str,
) -> CognitiveIntervention:
    seed = f"{tick_id}|{observer_id}|{action}|{target_entity_id}"
    digest = sha256(seed.encode("utf-8")).hexdigest()[:20]
    proposal_id = f"live-cog-{digest}"
    intervention_digest = sha256(
        f"{observer_id}|{action}|{target_entity_id}".encode("utf-8")
    ).hexdigest()[:24]
    return CognitiveIntervention(
        intervention_address=_addr("intervention", intervention_digest),
        proposal_id=proposal_id,
        action=action,
        target_entity_id=target_entity_id,
    )


def candidate_for_intervention(
    *,
    world: dict[str, Any],
    observer: dict[str, Any],
    target: dict[str, Any],
    intervention: CognitiveIntervention,
) -> CognitiveCandidate:
    before = observer_state_addresses(world, observer)
    target_id = str(target.get("id") or intervention.target_entity_id)
    target_region = str(target.get("region_id") or "").strip()

    next_values = [
        value
        for value in before
        if not value.startswith("live:region:") and not value.startswith("live:near:")
    ]
    if target_region:
        next_values.append(_addr("region", target_region))
    next_values.append(_addr("near", target_id))
    next_values.append(_addr("action", intervention.action))
    next_state = _stable_unique(next_values)

    before_set = set(before)
    consequences = tuple(value for value in next_state if value not in before_set)
    if not consequences:
        consequences = (_addr("outcome", "no-structural-change"),)

    candidate_digest = sha256(
        f"{intervention.proposal_id}|{'|'.join(next_state)}".encode("utf-8")
    ).hexdigest()[:20]
    return CognitiveCandidate(
        candidate_id=f"candidate-{candidate_digest}",
        proposal_id=intervention.proposal_id,
        consequence_addresses=consequences,
        next_state_addresses=next_state,
    )


def build_nov_cognitive_frame(
    *,
    world: dict[str, Any],
    observer: dict[str, Any],
    targets: dict[str, dict[str, Any]],
    context_digest: str | None = None,
    event_ids: Iterable[str] = (),
) -> CognitiveFrame:
    observer_id = str(observer.get("id") or "").strip()
    if observer_id != "nov":
        raise ValueError("production cognitive frame currently supports observer 'nov' only")

    tick_id = int(world.get("current_tick", world.get("sequence", 0)) or 0)
    state = observer_state_addresses(world, observer)
    interventions: list[CognitiveIntervention] = []
    candidates: list[CognitiveCandidate] = []

    for action in NOV_ACTIONS:
        target_id = target_for_action(action, observer)
        target = targets.get(target_id)
        if not isinstance(target, dict):
            continue
        intervention = intervention_for_action(
            tick_id=tick_id,
            observer_id=observer_id,
            action=action,
            target_entity_id=target_id,
        )
        interventions.append(intervention)
        candidates.append(
            candidate_for_intervention(
                world=world,
                observer=observer,
                target=target,
                intervention=intervention,
            )
        )

    frame_seed = "|".join(
        [
            str(tick_id),
            observer_id,
            str(world.get("version", 0)),
            str(world.get("sequence", 0)),
            str(world.get("state_hash") or ""),
            *state,
            *(item.proposal_id for item in interventions),
        ]
    )
    frame_id = f"cf_{sha256(frame_seed.encode('utf-8')).hexdigest()[:24]}"

    return CognitiveFrame(
        frame_id=frame_id,
        tick_id=tick_id,
        observer_id=observer_id,
        state_addresses=state,
        available_interventions=tuple(interventions),
        candidate_outcomes=tuple(candidates),
        provenance={
            "world_version": int(world.get("version", 0)),
            "world_sequence": int(world.get("sequence", 0)),
            "world_state_hash": world.get("state_hash"),
            "context_digest": context_digest,
            "event_ids": tuple(sorted(set(str(value) for value in event_ids if value))),
            "authority": "read-only-cognitive-projection",
        },
    )


def to_memoria_v2_request_payload(frame: CognitiveFrame, *, proposal_id: str) -> dict[str, Any]:
    matches = tuple(
        item for item in frame.available_interventions if item.proposal_id == proposal_id
    )
    if len(matches) != 1:
        raise ValueError("proposal_id must identify exactly one available intervention")
    intervention = matches[0]
    candidates = tuple(
        item for item in frame.candidate_outcomes if item.proposal_id == proposal_id
    )
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
