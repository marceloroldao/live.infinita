from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from reality_slice import ContextAssociation, SparseContextAssociator, TemporalAssociator


@dataclass(frozen=True, slots=True)
class HigherOrderContextPolicy:
    min_repetitions: int = 3
    min_independent_slices: int = 3
    min_rho: float = 0.39
    min_context_reliability: float = 0.75
    max_lower_order_reliability: float = 0.75
    context_span: float = 0.15
    max_consequence_delay: float = 1.5
    min_pattern_support: int = 1
    forgetting_lambda0: float = 0.0
    forgetting_consolidation: float = 1.0
    active_evidence_slice_window: int = 0
    active_evidence_time_window: float = 0.0


@dataclass(frozen=True, slots=True)
class HigherOrderContextCandidate:
    candidate_id: str
    antecedent_patterns: tuple[int, int]
    consequence_pattern: int
    rho: float
    repetitions: int
    context_coverage: float
    temporal_stability: float
    context_reliability: float
    lower_order_reliabilities: tuple[float, float]
    mean_delay: float
    variance_delay: float
    supporting_slice_ids: tuple[int, ...]
    supporting_frame_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "antecedent_pattern_addresses": tuple(
                f"temporal:pattern:{value}"
                for value in self.antecedent_patterns
            ),
            "consequence_pattern_address": (
                f"temporal:pattern:{self.consequence_pattern}"
            ),
            "evidence": {
                "rho": self.rho,
                "repetitions": self.repetitions,
                "context_coverage": self.context_coverage,
                "temporal_stability": self.temporal_stability,
                "context_reliability": self.context_reliability,
                "lower_order_reliabilities": self.lower_order_reliabilities,
                "mean_delay": self.mean_delay,
                "variance_delay": self.variance_delay,
            },
            "provenance": {
                "slice_ids": self.supporting_slice_ids,
                "frame_ids": self.supporting_frame_ids,
            },
        }


def policy_from_world(world: dict[str, Any]) -> HigherOrderContextPolicy:
    raw = (world.get("rules") or {}).get("higher_order_context_selector") or {}
    policy = HigherOrderContextPolicy(
        min_repetitions=int(raw.get("min_repetitions", 3)),
        min_independent_slices=int(raw.get("min_independent_slices", 3)),
        min_rho=float(raw.get("min_rho", 0.39)),
        min_context_reliability=float(
            raw.get("min_context_reliability", 0.75)
        ),
        max_lower_order_reliability=float(
            raw.get("max_lower_order_reliability", 0.75)
        ),
        context_span=float(raw.get("context_span", 0.15)),
        max_consequence_delay=float(raw.get("max_consequence_delay", 1.5)),
        min_pattern_support=int(raw.get("min_pattern_support", 1)),
        forgetting_lambda0=float(raw.get("forgetting_lambda0", 0.0)),
        forgetting_consolidation=float(
            raw.get("forgetting_consolidation", 1.0)
        ),
        active_evidence_slice_window=int(
            raw.get("active_evidence_slice_window", 0)
        ),
        active_evidence_time_window=float(
            raw.get("active_evidence_time_window", 0.0)
        ),
    )
    if (
        policy.min_repetitions < 1
        or policy.min_independent_slices < 1
        or policy.min_pattern_support < 1
        or policy.active_evidence_slice_window < 0
    ):
        raise ValueError("higher-order count/support thresholds must be >= 1")
    for name in (
        "min_rho",
        "min_context_reliability",
        "max_lower_order_reliability",
        "context_span",
        "max_consequence_delay",
        "forgetting_lambda0",
        "forgetting_consolidation",
        "active_evidence_time_window",
    ):
        if getattr(policy, name) < 0:
            raise ValueError(f"{name} must be >= 0")
    if policy.min_rho > 1 or policy.min_context_reliability > 1:
        raise ValueError("higher-order probability-like thresholds must be <= 1")
    if policy.max_lower_order_reliability > 1:
        raise ValueError("max_lower_order_reliability must be <= 1")
    if policy.max_consequence_delay <= 0:
        raise ValueError("max_consequence_delay must be > 0")
    if (
        policy.active_evidence_slice_window > 0
        and policy.active_evidence_time_window > 0
    ):
        raise ValueError(
            "configure either active_evidence_slice_window or "
            "active_evidence_time_window, not both"
        )
    return policy


def make_sparse_context_associator(
    policy: HigherOrderContextPolicy,
    *,
    lambda0: float | None = None,
) -> SparseContextAssociator:
    effective_lambda0 = (
        policy.forgetting_lambda0
        if lambda0 is None
        else float(lambda0)
    )
    return SparseContextAssociator(
        lambda0=effective_lambda0,
        consolidation=policy.forgetting_consolidation,
        context_span=policy.context_span,
        max_consequence_delay=policy.max_consequence_delay,
        min_pattern_support=policy.min_pattern_support,
    )


def _candidate_id(link: ContextAssociation) -> str:
    seed = "|".join(
        (
            str(link.antecedents[0]),
            str(link.antecedents[1]),
            str(link.consequence),
        )
    )
    return "hoc_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


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



def _active_slice_ids(
    higher: SparseContextAssociator,
    policy: HigherOrderContextPolicy,
) -> tuple[int, ...] | None:
    if policy.active_evidence_time_window > 0:
        return higher.recent_slice_ids_by_time(
            policy.active_evidence_time_window
        )
    if policy.active_evidence_slice_window > 0:
        return higher.recent_slice_ids(
            policy.active_evidence_slice_window
        )
    return None


def select_higher_order_context_candidates(
    pairwise: TemporalAssociator,
    higher: SparseContextAssociator,
    policy: HigherOrderContextPolicy,
    *,
    provenance_by_slice: Mapping[int, Sequence[str]] | None = None,
) -> tuple[HigherOrderContextCandidate, ...]:
    """Package only bit.analyze contexts admitted beyond insufficient lower-order links."""
    active_slice_ids = _active_slice_ids(higher, policy)
    active_set = (
        None
        if active_slice_ids is None
        else set(int(value) for value in active_slice_ids)
    )

    admitted = higher.admitted_contexts(
        pairwise,
        min_repetitions=policy.min_repetitions,
        min_independent_slices=policy.min_independent_slices,
        min_rho=policy.min_rho,
        min_context_reliability=policy.min_context_reliability,
        max_lower_order_reliability=policy.max_lower_order_reliability,
        active_slice_ids=active_slice_ids,
    )

    values: list[HigherOrderContextCandidate] = []
    for link in admitted:
        slice_ids = tuple(
            sorted(
                int(value)
                for value in (
                    link.seen_slices
                    if active_set is None
                    else link.seen_slices & active_set
                )
            )
        )
        values.append(
            HigherOrderContextCandidate(
                candidate_id=_candidate_id(link),
                antecedent_patterns=link.antecedents,
                consequence_pattern=link.consequence,
                rho=link.rho,
                repetitions=(
                    link.repetitions
                    if active_set is None
                    else len(link.seen_slices & active_set)
                ),
                context_coverage=higher.context_coverage(
                    link,
                    active_slice_ids,
                ),
                temporal_stability=higher.temporal_stability(link),
                context_reliability=(
                    higher.context_coverage(link, active_slice_ids)
                    * higher.temporal_stability(link)
                ),
                lower_order_reliabilities=tuple(
                    higher.lower_order_reliabilities(link, pairwise)
                ),
                mean_delay=link.mean_delay,
                variance_delay=link.variance_delay,
                supporting_slice_ids=slice_ids,
                supporting_frame_ids=_supporting_frames(
                    slice_ids,
                    provenance_by_slice,
                ),
            )
        )

    values.sort(
        key=lambda item: (
            item.antecedent_patterns,
            item.consequence_pattern,
            item.candidate_id,
        )
    )
    return tuple(values)



@dataclass(frozen=True, slots=True)
class HigherOrderContextCurrentHypothesis:
    candidate_id: str
    consequence_pattern: int
    rho: float
    repetitions: int
    context_coverage: float
    context_reliability: float
    supporting_slice_ids: tuple[int, ...]
    admitted: bool


@dataclass(frozen=True, slots=True)
class HigherOrderContextResolution:
    antecedent_patterns: tuple[int, int]
    resolution_state: str
    active_candidate_ids: tuple[str, ...]
    competing_candidate_ids: tuple[str, ...]
    hypotheses: tuple[HigherOrderContextCurrentHypothesis, ...]


def resolve_higher_order_context_states(
    pairwise: TemporalAssociator,
    higher: SparseContextAssociator,
    policy: HigherOrderContextPolicy,
) -> tuple[HigherOrderContextResolution, ...]:
    """Describe current resolved/ambiguous/unsupported state for each known context.

    This is a read-only projection over higher-order structural evidence. It does not
    create links, observations, candidate identities or semantic regime labels.
    """
    active_slice_ids = (
        higher.recent_slice_ids(policy.active_evidence_slice_window)
        if policy.active_evidence_slice_window > 0
        else None
    )
    active_set = (
        None
        if active_slice_ids is None
        else set(int(value) for value in active_slice_ids)
    )
    admitted_links = set(
        id(link)
        for link in higher.admitted_contexts(
            pairwise,
            min_repetitions=policy.min_repetitions,
            min_independent_slices=policy.min_independent_slices,
            min_rho=policy.min_rho,
            min_context_reliability=policy.min_context_reliability,
            max_lower_order_reliability=policy.max_lower_order_reliability,
            active_slice_ids=active_slice_ids,
        )
    )

    by_context: dict[
        tuple[int, int],
        list[HigherOrderContextCurrentHypothesis],
    ] = {}
    for _key, link in sorted(higher.links.items()):
        lower_order = higher.lower_order_reliabilities(link, pairwise)
        if any(
            value >= policy.max_lower_order_reliability
            for value in lower_order
        ):
            continue
        support_slices = (
            set(link.seen_slices)
            if active_set is None
            else set(link.seen_slices) & active_set
        )
        if not support_slices:
            continue
        coverage = higher.context_coverage(link, active_slice_ids)
        reliability = coverage * higher.temporal_stability(link)
        by_context.setdefault(link.antecedents, []).append(
            HigherOrderContextCurrentHypothesis(
                candidate_id=_candidate_id(link),
                consequence_pattern=link.consequence,
                rho=link.rho,
                repetitions=(
                    link.repetitions
                    if active_set is None
                    else len(support_slices)
                ),
                context_coverage=coverage,
                context_reliability=reliability,
                supporting_slice_ids=tuple(sorted(int(x) for x in support_slices)),
                admitted=id(link) in admitted_links,
            )
        )

    resolutions: list[HigherOrderContextResolution] = []
    for antecedents, raw_hypotheses in sorted(by_context.items()):
        hypotheses = tuple(
            sorted(
                raw_hypotheses,
                key=lambda item: (
                    item.consequence_pattern,
                    item.candidate_id,
                ),
            )
        )
        admitted_ids = tuple(
            sorted(
                item.candidate_id
                for item in hypotheses
                if item.admitted
            )
        )

        if len(admitted_ids) == 1:
            state = "resolved"
            active_ids = admitted_ids
            competing_ids: tuple[str, ...] = ()
        elif len(admitted_ids) > 1:
            state = "ambiguous"
            active_ids = ()
            competing_ids = admitted_ids
        elif len(hypotheses) >= 2:
            state = "ambiguous"
            active_ids = ()
            competing_ids = tuple(
                sorted(item.candidate_id for item in hypotheses)
            )
        else:
            state = "unsupported"
            active_ids = ()
            competing_ids = ()

        resolutions.append(
            HigherOrderContextResolution(
                antecedent_patterns=antecedents,
                resolution_state=state,
                active_candidate_ids=active_ids,
                competing_candidate_ids=competing_ids,
                hypotheses=hypotheses,
            )
        )
    return tuple(resolutions)
