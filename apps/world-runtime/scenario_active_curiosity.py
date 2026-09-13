from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class ActiveWorldOption:
    proposal_id: str
    intervention_address: str
    possible_outcomes: tuple[tuple[str, ...], ...]


def _intervention_address(actor: str, action: str, target: str | None) -> str:
    raw = f"{actor}|{action}|{target if target is not None else ''}"
    digest = sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"live:intervention:{digest}"


def build_active_curiosity_scenario() -> dict:
    """World-owned options for the first active V2 experiment.

    The world exposes two valid interventions. One can discriminate between the two
    active hypotheses (X versus Y); the other has only a shared/no-change outcome and
    therefore carries no discriminative information for this uncertainty.
    """
    informative = ActiveWorldOption(
        proposal_id="proposal-probe",
        intervention_address=_intervention_address("nova", "probe", "fire"),
        possible_outcomes=(("live:effect:x",), ("live:effect:y",)),
    )
    neutral = ActiveWorldOption(
        proposal_id="proposal-wait",
        intervention_address=_intervention_address("nova", "wait", None),
        possible_outcomes=(("live:outcome:no-structural-change",),),
    )
    return {
        "observer_id": "nova",
        "hypotheses": (
            ("H-X", ("live:effect:x",)),
            ("H-Y", ("live:effect:y",)),
        ),
        "options": (informative, neutral),
        "world_results": {
            informative.intervention_address: ("live:effect:y",),
            neutral.intervention_address: ("live:outcome:no-structural-change",),
        },
        "expected_selected_proposal_id": informative.proposal_id,
        "expected_selected_intervention": informative.intervention_address,
        "expected_survivor": "H-Y",
    }
