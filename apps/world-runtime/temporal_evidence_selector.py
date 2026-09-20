from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from reality_slice import Association, TemporalAssociator


@dataclass(frozen=True, slots=True)
class TemporalEvidencePolicy:
    min_repetitions: int
    min_independent_slices: int
    min_rho: float
    min_selectivity: float
    min_temporal_stability: float
    min_evidence_score: float
    min_direction_confidence: float


@dataclass(frozen=True, slots=True)
class TemporalEvidenceCandidate:
    candidate_id: str
    pattern_a: int
    pattern_b: int
    orientation: str
    orientation_confidence: float
    rho: float
    repetitions: int
    selectivity: float
    temporal_stability: float
    evidence_score: float
    mean_dt: float
    variance_dt: float
    supporting_slice_ids: tuple[int, ...]
    supporting_frame_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        """Transport-neutral candidate contract for a future Memoria.ia bridge.

        Pattern IDs and temporal evidence are structural only. No semantic predicate,
        causal label, natural-language meaning, or fabricated intervention is emitted.
        """
        return {
            "candidate_id": self.candidate_id,
            "pattern_addresses": (
                f"temporal:pattern:{self.pattern_a}",
                f"temporal:pattern:{self.pattern_b}",
            ),
            "orientation": self.orientation,
            "orientation_confidence": self.orientation_confidence,
            "evidence": {
                "rho": self.rho,
                "repetitions": self.repetitions,
                "selectivity": self.selectivity,
                "temporal_stability": self.temporal_stability,
                "evidence_score": self.evidence_score,
                "mean_dt": self.mean_dt,
                "variance_dt": self.variance_dt,
            },
            "provenance": {
                "slice_ids": self.supporting_slice_ids,
                "frame_ids": self.supporting_frame_ids,
            },
        }


@dataclass(frozen=True, slots=True)
class TemporalEvidenceDecision:
    pattern_a: int
    pattern_b: int
    admitted: bool
    rejection_reasons: tuple[str, ...]
    candidate: TemporalEvidenceCandidate | None


def policy_from_world(world: dict[str, Any]) -> TemporalEvidencePolicy:
    raw = (world.get("rules") or {}).get("temporal_evidence_selector") or {}
    policy = TemporalEvidencePolicy(
        min_repetitions=int(raw.get("min_repetitions", 3)),
        min_independent_slices=int(raw.get("min_independent_slices", 3)),
        min_rho=float(raw.get("min_rho", 0.39)),
        min_selectivity=float(raw.get("min_selectivity", 0.80)),
        min_temporal_stability=float(raw.get("min_temporal_stability", 0.90)),
        min_evidence_score=float(raw.get("min_evidence_score", 3.0)),
        min_direction_confidence=float(raw.get("min_direction_confidence", 0.80)),
    )
    if policy.min_repetitions < 1 or policy.min_independent_slices < 1:
        raise ValueError("temporal evidence count thresholds must be >= 1")
    for name in (
        "min_rho",
        "min_selectivity",
        "min_temporal_stability",
        "min_evidence_score",
        "min_direction_confidence",
    ):
        if getattr(policy, name) < 0:
            raise ValueError(f"{name} must be >= 0")
    if policy.min_direction_confidence > 1:
        raise ValueError("min_direction_confidence must be <= 1")
    return policy


def _orientation(link: Association) -> tuple[str, float]:
    forward, simultaneous, backward = link.direction_probabilities()
    ranked = sorted(
        (
            ("a_before_b", forward),
            ("simultaneous", simultaneous),
            ("b_before_a", backward),
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[0]


def _candidate_id(link: Association, orientation: str) -> str:
    seed = f"{link.a}|{link.b}|{orientation}"
    return "tec_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def _supporting_frames(
    slice_ids: Sequence[int],
    provenance_by_slice: Mapping[int, Sequence[str]] | None,
) -> tuple[str, ...]:
    if not provenance_by_slice:
        return ()
    output: list[str] = []
    seen: set[str] = set()
    for slice_id in slice_ids:
        for frame_id in provenance_by_slice.get(slice_id, ()):
            value = str(frame_id)
            if value and value not in seen:
                seen.add(value)
                output.append(value)
    return tuple(output)


def evaluate_temporal_association(
    engine: TemporalAssociator,
    link: Association,
    policy: TemporalEvidencePolicy,
    *,
    provenance_by_slice: Mapping[int, Sequence[str]] | None = None,
) -> TemporalEvidenceDecision:
    selectivity = engine.selectivity(link)
    stability = engine.temporal_stability(link)
    score = engine.evidence_score(link)
    orientation, confidence = _orientation(link)
    slice_ids = tuple(sorted(int(item) for item in link.seen_slices))

    reasons: list[str] = []
    if link.repetitions < policy.min_repetitions:
        reasons.append("insufficient-repetitions")
    if len(slice_ids) < policy.min_independent_slices:
        reasons.append("insufficient-independent-slices")
    if link.rho < policy.min_rho:
        reasons.append("insufficient-rho")
    if selectivity < policy.min_selectivity:
        reasons.append("insufficient-selectivity")
    if stability < policy.min_temporal_stability:
        reasons.append("insufficient-temporal-stability")
    if score < policy.min_evidence_score:
        reasons.append("insufficient-evidence-score")
    if confidence < policy.min_direction_confidence:
        reasons.append("insufficient-direction-confidence")

    if reasons:
        return TemporalEvidenceDecision(
            pattern_a=link.a,
            pattern_b=link.b,
            admitted=False,
            rejection_reasons=tuple(reasons),
            candidate=None,
        )

    candidate = TemporalEvidenceCandidate(
        candidate_id=_candidate_id(link, orientation),
        pattern_a=link.a,
        pattern_b=link.b,
        orientation=orientation,
        orientation_confidence=confidence,
        rho=link.rho,
        repetitions=link.repetitions,
        selectivity=selectivity,
        temporal_stability=stability,
        evidence_score=score,
        mean_dt=link.mean_dt,
        variance_dt=link.variance_dt,
        supporting_slice_ids=slice_ids,
        supporting_frame_ids=_supporting_frames(slice_ids, provenance_by_slice),
    )
    return TemporalEvidenceDecision(
        pattern_a=link.a,
        pattern_b=link.b,
        admitted=True,
        rejection_reasons=(),
        candidate=candidate,
    )


def select_temporal_evidence_candidates(
    engine: TemporalAssociator,
    policy: TemporalEvidencePolicy,
    *,
    provenance_by_slice: Mapping[int, Sequence[str]] | None = None,
) -> tuple[TemporalEvidenceDecision, ...]:
    decisions = [
        evaluate_temporal_association(
            engine,
            link,
            policy,
            provenance_by_slice=provenance_by_slice,
        )
        for _key, link in sorted(engine.links.items())
    ]
    decisions.sort(key=lambda item: (item.pattern_a, item.pattern_b))
    return tuple(decisions)


def admitted_candidates(
    decisions: Sequence[TemporalEvidenceDecision],
) -> tuple[TemporalEvidenceCandidate, ...]:
    values = [
        item.candidate
        for item in decisions
        if item.admitted and item.candidate is not None
    ]
    values.sort(key=lambda item: item.candidate_id)
    return tuple(values)
