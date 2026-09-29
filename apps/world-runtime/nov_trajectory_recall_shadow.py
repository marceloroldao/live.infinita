"""MVP-018H — evidence-driven trajectory recall comparison (no action authority).

Operate only on already verified typed V2 records from the owner-private cache.
A trajectory profile is the *observed* address vector plus its raw, typed
outcome vector; no hand-authored success threshold or inferred predicate.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any

from nov_memory_recall_shadow import FIELDS, RecallBlocked

OUTCOME_FIELDS = ("satisfaction", "observed_risk", "elapsed_ticks", "preemptions", "replans")
MAX_SELECTION = 8


def address_signature(row: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    addresses = row.get("addresses")
    if not isinstance(addresses, dict):
        raise RecallBlocked("invalid_address_vector")
    vector = []
    for key in FIELDS:
        value = addresses.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise RecallBlocked("invalid_address_value")
        vector.append((key, value))
    return tuple(vector)


def outcome_signature(row: dict[str, Any]) -> tuple[tuple[str, int | float | None], ...]:
    observation = row.get("observation")
    if not isinstance(observation, dict):
        raise RecallBlocked("missing_typed_observation")
    outcome = observation.get("outcome")
    if not isinstance(outcome, dict):
        raise RecallBlocked("missing_typed_outcome")
    result = []
    for key in OUTCOME_FIELDS:
        value = outcome.get(key)
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise RecallBlocked("invalid_typed_outcome")
        result.append((key, value))
    return tuple(result)


def trajectory_signature(row: dict[str, Any]) -> tuple[
    tuple[tuple[str, str], ...],
    tuple[tuple[str, int | float | None], ...],
]:
    return address_signature(row), outcome_signature(row)


def compare_trajectory_recall(
    records: list[dict[str, Any]], *, query: dict[str, str],
    exclude_key: str | None, limit: int = 5,
) -> dict[str, Any]:
    """One representative per observed profile, then fill remaining slots by recency.

    Same candidate pool, address-intersection relevance and proven source as
    baseline; this comparator only changes coverage of actually seen profiles.
    Full-match/partial-match counts remain visible for later analysis.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_SELECTION:
        raise RecallBlocked("invalid_trajectory_limit")
    if not query or not set(query).issubset(FIELDS):
        raise RecallBlocked("invalid_trajectory_query")
    if not all(isinstance(value, str) and value for value in query.values()):
        raise RecallBlocked("invalid_trajectory_query")
    matched = []
    for row in records:
        if row.get("record_key") == exclude_key:
            continue
        tick = row.get("logical_tick")
        if type(tick) is not int or tick < 0:
            raise RecallBlocked("invalid_trajectory_tick")
        address = dict(address_signature(row))
        profile = trajectory_signature(row)
        shared = tuple(name for name, value in query.items() if address.get(name) == value)
        if shared:
            matched.append((row, shared, profile))
    matched.sort(key=lambda item: (
        -len(item[1]), -item[0]["logical_tick"], item[0]["record_key"],
    ))
    baseline = matched[:limit]
    diversified = []
    covered = set()
    for item in matched:
        if item[2] not in covered:
            diversified.append(item)
            covered.add(item[2])
            if len(diversified) == limit:
                break
    if len(diversified) < limit:
        chosen = {row["record_key"] for row, _, _ in diversified}
        for item in matched:
            if item[0]["record_key"] not in chosen:
                diversified.append(item)
                chosen.add(item[0]["record_key"])
                if len(diversified) == limit:
                    break

    def counts(items):
        return {
            "retrieved_count": len(items),
            "unique_address_profiles": len({item[2][0] for item in items}),
            "unique_observed_trajectory_profiles": len({item[2] for item in items}),
            "full_address_matches": sum(len(item[1]) == len(query) for item in items),
            "partial_address_matches": sum(len(item[1]) < len(query) for item in items),
            "overlap_counts": [len(item[1]) for item in items],
        }

    baseline_counts, diverse_counts = counts(baseline), counts(diversified)
    if baseline_counts["retrieved_count"] != diverse_counts["retrieved_count"]:
        raise RecallBlocked("trajectory_comparison_count_mismatch")
    return {
        "matching_records": len(matched),
        "candidate_address_profiles": len({item[2][0] for item in matched}),
        "candidate_outcome_profiles": len({item[2][1] for item in matched}),
        "candidate_trajectory_profiles": len({item[2] for item in matched}),
        "baseline": baseline_counts,
        "diversified": diverse_counts,
        "selection_authority": False,
        "causal_inference_claim": False,
        "new_evidence_created": False,
    }


def trajectory_distribution(records: list[dict[str, Any]]) -> dict[str, int]:
    """Only counts and recurrence; no addresses or raw outcome values escape."""
    ordered = sorted(records, key=lambda row: (row["logical_tick"], row["record_key"]))
    address_vectors = [address_signature(row) for row in ordered]
    outcome_vectors = [outcome_signature(row) for row in ordered]
    profiles = list(zip(address_vectors, outcome_vectors))
    recurrence = Counter(profiles)
    transitions = Counter(zip(address_vectors, address_vectors[1:]))
    return {
        "unique_observed_outcome_profiles": len(set(outcome_vectors)),
        "unique_observed_trajectory_profiles": len(recurrence),
        "largest_identical_trajectory_profile_group": max(recurrence.values(), default=0),
        "observed_address_transitions": len(ordered) - 1 if ordered else 0,
        "distinct_directed_address_transitions": len(transitions),
        "self_address_transitions": sum(
            count for (before, after), count in transitions.items() if before == after
        ),
    }
