"""MVP-018I: opt-in owner-process hybrid recall, read-only and non-authoritative.

The first two highest-relevance results are anchored. Remaining slots cover
distinct *observed* address+outcome profiles only inside the exact address-
overlap stratum occupied by the corresponding baseline slot. Therefore the
full/partial relevance vector is identical to the recency baseline.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from memoria_v2_adapter import CognitiveFrame
from nov_memory_context_shadow import freeze_memory_context
from nov_memory_recall_cache import VersionedNovRecallCache, frame_query
from nov_memory_recall_shadow import FIELDS, RecallBlocked, SCHEMA as RECALL_SCHEMA
from nov_trajectory_recall_shadow import trajectory_signature

MAX_HYBRID_SELECTION = 5
DEFAULT_ANCHORS = 2


def _matching_rows(
    records: list[dict[str, Any]], *, query: dict[str, str],
    exclude_key: str | None,
) -> list[tuple[dict[str, Any], tuple[str, ...], tuple[Any, ...]]]:
    if not query or not set(query).issubset(FIELDS):
        raise RecallBlocked("hybrid_invalid_query")
    if any(not isinstance(v, str) or not v for v in query.values()):
        raise RecallBlocked("hybrid_invalid_address")
    pool = []
    keys: set[str] = set()
    for row in records:
        key = row.get("record_key")
        tick = row.get("logical_tick")
        if not isinstance(key, str) or not key or key in keys:
            raise RecallBlocked("hybrid_record_key")
        keys.add(key)
        if type(tick) is not int or tick < 0:
            raise RecallBlocked("hybrid_tick")
        # Even non-matches must satisfy typed provenance; this input must be
        # the V2-validated owner index, never text/LLM-derived episodes.
        profile = trajectory_signature(row)
        if key == exclude_key:
            continue
        address = dict(profile[0])
        overlap = tuple(sorted(field for field, value in query.items()
                               if address.get(field) == value))
        if overlap:
            pool.append((row, overlap, profile))
    pool.sort(key=lambda item: (
        -len(item[1]), -item[0]["logical_tick"], item[0]["record_key"],
    ))
    return pool


def select_hybrid(
    records: list[dict[str, Any]], *, query: dict[str, str],
    exclude_key: str | None, limit: int = MAX_HYBRID_SELECTION,
    anchors: int = DEFAULT_ANCHORS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Private selected records plus aggregate-only diagnostic summary.

    Slots may only be substituted by a candidate with the same number of
    matching addresses as the baseline for that slot. No score threshold,
    invented success classification or change to full-match count.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_HYBRID_SELECTION:
        raise RecallBlocked("hybrid_limit")
    if type(anchors) is not int or not 1 <= anchors <= limit:
        raise RecallBlocked("hybrid_anchor_budget")
    pool = _matching_rows(records, query=query, exclude_key=exclude_key)
    baseline = pool[:limit]
    chosen = baseline[:anchors]
    used = {item[0]["record_key"] for item in chosen}
    profiles = {item[2] for item in chosen}
    diversity_slots = 0
    for slot in baseline[len(chosen):]:
        overlap_size = len(slot[1])
        band = (item for item in pool
                if len(item[1]) == overlap_size and item[0]["record_key"] not in used)
        available = list(band)
        candidate = next((item for item in available if item[2] not in profiles), None)
        if candidate is not None:
            diversity_slots += 1
        else:
            candidate = available[0] if available else None
        if candidate is None:
            raise RecallBlocked("hybrid_band_exhausted")
        chosen.append(candidate)
        used.add(candidate[0]["record_key"])
        profiles.add(candidate[2])
    before = [len(item[1]) for item in baseline]
    after = [len(item[1]) for item in chosen]
    if before != after or len(chosen) != len(baseline) or len(used) != len(chosen):
        raise RecallBlocked("hybrid_relevance_invariant")
    selected = [{**item[0], "matching_addresses": item[1]} for item in chosen]
    stats = {
        "matching_records": len(pool),
        "baseline_retrieved": len(baseline),
        "hybrid_retrieved": len(chosen),
        "anchored_slots": min(anchors, len(baseline)),
        "diversified_slots": diversity_slots,
        "baseline_trajectory_profiles": len({item[2] for item in baseline}),
        "hybrid_trajectory_profiles": len({item[2] for item in chosen}),
        "baseline_overlap_counts": before,
        "hybrid_overlap_counts": after,
        "baseline_full_matches": before.count(len(query)),
        "hybrid_full_matches": after.count(len(query)),
        "relevance_vector_preserved": before == after,
        "selection_authority": False,
        "causal_inference_claim": False,
        "new_evidence_created": False,
    }
    return selected, stats


@dataclass(slots=True, repr=False)
class OwnerHybridRecallWorker:
    """Explicitly invoked by an owner-side process, never the world tick.

    No loop/timer is created here. The caller schedules refreshes externally;
    every call checks the private cache version and revalidates changed data
    with the pinned V2. Contents remain in the service-account process.
    """
    cache: VersionedNovRecallCache = field(repr=False)
    anchors: int = DEFAULT_ANCHORS

    def refresh(self, frame: CognitiveFrame) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.cache._lock:
            before = self.cache._current_version()
            baseline = self.cache(frame)
            records = [
                row for row in self.cache._validated_index
                if row["logical_tick"] <= frame.tick_id
            ]
            if records:
                seed = max(records, key=lambda row: (row["logical_tick"], row["record_key"]))
                query = frame_query(frame, seed)
            else:
                query, seed = {}, None
            if query:
                selected, metrics = select_hybrid(
                    records, query=query, exclude_key=seed["record_key"],
                    limit=MAX_HYBRID_SELECTION, anchors=self.anchors,
                )
            else:
                selected = []
                metrics = {
                    "matching_records": 0, "baseline_retrieved": 0,
                    "hybrid_retrieved": 0, "anchored_slots": 0,
                    "diversified_slots": 0, "baseline_trajectory_profiles": 0,
                    "hybrid_trajectory_profiles": 0, "baseline_overlap_counts": [],
                    "hybrid_overlap_counts": [], "baseline_full_matches": 0,
                    "hybrid_full_matches": 0, "relevance_vector_preserved": True,
                    "selection_authority": False, "causal_inference_claim": False,
                    "new_evidence_created": False,
                }
            if metrics["matching_records"] != baseline["historical_matches"]:
                raise RecallBlocked("hybrid_baseline_count_mismatch")
            if metrics["baseline_overlap_counts"] != [
                row["matched_address_count"] for row in baseline["selected"]
            ]:
                raise RecallBlocked("hybrid_baseline_relevance_mismatch")
            if self.cache._current_version() != before:
                self.cache.invalidate()
                raise RecallBlocked("hybrid_source_moved")
            result = {
                **{key: value for key, value in baseline.items()
                   if key not in ("selected", "private_evidence")},
                "schema": RECALL_SCHEMA,
                "selected": [{
                    "logical_tick": row["logical_tick"],
                    "matched_address_count": len(row["matching_addresses"]),
                    "source": "typed_confirmed_nov_outcome",
                } for row in selected],
                "private_evidence": [{
                    "record_key": row["record_key"],
                    "evidence_id": row["evidence_id"],
                    "content_sha256": row["content_sha256"],
                    "logical_tick": row["logical_tick"],
                    "observation": deepcopy(row["observation"]),
                    "matching_addresses": list(row["matching_addresses"]),
                    "provenance": "live.infinita:npc_episode_v1",
                    "world_id": before.world_id,
                } for row in selected],
            }
            verified = freeze_memory_context(frame, result)
            if verified.public_view["evidence_count"] != metrics["hybrid_retrieved"]:
                raise RecallBlocked("hybrid_context_count_mismatch")
            return result, metrics
