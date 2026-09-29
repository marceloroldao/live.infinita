"""MVP-018J — two independently verified observational recall lanes.

The primary lane is the unmodified relevance-preserving MVP-018I selection.
The supplementary lane holds *additional* typed observed profiles, not action
candidates. A supplemental match is never used to replace a primary slot.
No background work, disk state, source writes or world-tick integration.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from memoria_v2_adapter import CognitiveFrame
from nov_memory_context_shadow import freeze_memory_context
from nov_memory_hybrid_shadow import OwnerHybridRecallWorker, _matching_rows
from nov_memory_recall_cache import VersionedNovRecallCache, frame_query
from nov_memory_recall_shadow import RecallBlocked
from nov_trajectory_recall_shadow import trajectory_signature

MAX_SUPPLEMENTARY = 3


def select_supplementary(
    records: list[dict[str, Any]], *, query: dict[str, str],
    exclude_key: str | None, primary: list[dict[str, Any]],
    limit: int = MAX_SUPPLEMENTARY,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One extra representative per real, not-already-present trajectory.

    The primary top-five remains untouched. Recency and address overlap
    order supplementary observations, not perceived outcome quality.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_SUPPLEMENTARY:
        raise RecallBlocked("supplementary_invalid_limit")
    primary_ids = {row.get("record_key") for row in primary}
    if len(primary_ids) != len(primary):
        raise RecallBlocked("supplementary_duplicate_primary")
    primary_profiles = {trajectory_signature(row) for row in primary}
    pool = _matching_rows(records, query=query, exclude_key=exclude_key)
    selected: list[dict[str, Any]] = []
    added_profiles: set[Any] = set()
    for row, overlap, profile in pool:
        if (row["record_key"] in primary_ids or profile in primary_profiles
                or profile in added_profiles):
            continue
        selected.append({**row, "matching_addresses": overlap})
        added_profiles.add(profile)
        if len(selected) >= limit:
            break
    if (len({row["record_key"] for row in selected}) != len(selected)
            or any(row["record_key"] in primary_ids for row in selected)):
        raise RecallBlocked("supplementary_identity_overlap")
    stats = {
        "supplementary_count": len(selected),
        "supplementary_distinct_observed_profiles": len(added_profiles),
        "supplementary_overlap_counts": [len(row["matching_addresses"]) for row in selected],
        "primary_count_unchanged": len(primary),
        "primary_observed_profiles": len(primary_profiles),
        "combined_distinct_observed_profiles": len(primary_profiles | added_profiles),
        "selection_authority": False,
        "causal_inference_claim": False,
        "supplementary_used_to_rank_primary": False,
        "new_evidence_created": False,
    }
    return selected, stats


@dataclass(slots=True, repr=False)
class OwnerDualLaneRecallObserver:
    """Explicit owner-side read-only process only; no scheduling or live wiring."""
    cache: VersionedNovRecallCache = field(repr=False)

    def refresh(self, frame: CognitiveFrame) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        with self.cache._lock:
            before = self.cache._current_version()
            primary, primary_stats = OwnerHybridRecallWorker(self.cache).refresh(frame)
            records = [
                row for row in self.cache._validated_index
                if type(row.get("logical_tick")) is int and row["logical_tick"] <= frame.tick_id
            ]
            if records:
                seed = max(records, key=lambda row: (row["logical_tick"], row["record_key"]))
                query = frame_query(frame, seed)
            else:
                seed, query = None, {}
            if query:
                primary_keys = {row["record_key"] for row in primary["private_evidence"]}
                primary_rows = [row for row in records if row["record_key"] in primary_keys]
                if len(primary_rows) != len(primary_keys):
                    raise RecallBlocked("supplementary_primary_index_mismatch")
                secondary, secondary_stats = select_supplementary(
                    records, query=query, exclude_key=seed["record_key"],
                    primary=primary_rows,
                )
            else:
                secondary = []
                secondary_stats = {
                    "supplementary_count": 0,
                    "supplementary_distinct_observed_profiles": 0,
                    "supplementary_overlap_counts": [],
                    "primary_count_unchanged": len(primary["selected"]),
                    "primary_observed_profiles": 0,
                    "combined_distinct_observed_profiles": 0,
                    "selection_authority": False,
                    "causal_inference_claim": False,
                    "supplementary_used_to_rank_primary": False,
                    "new_evidence_created": False,
                }
            supplement = {
                **{key: value for key, value in primary.items()
                   if key not in ("selected", "private_evidence")},
                "selected": [{
                    "logical_tick": row["logical_tick"],
                    "matched_address_count": len(row["matching_addresses"]),
                    "source": "typed_confirmed_nov_outcome",
                } for row in secondary],
                "private_evidence": [{
                    "record_key": row["record_key"],
                    "evidence_id": row["evidence_id"],
                    "content_sha256": row["content_sha256"],
                    "logical_tick": row["logical_tick"],
                    "observation": deepcopy(row["observation"]),
                    "matching_addresses": list(row["matching_addresses"]),
                    "provenance": "live.infinita:npc_episode_v1",
                    "world_id": before.world_id,
                } for row in secondary],
            }
            # Distinct private contexts: never make supplementary rows look
            # like core baseline evidence or give them selection authority.
            primary_context = freeze_memory_context(frame, primary)
            additional_context = freeze_memory_context(frame, supplement)
            if (primary_context.public_view["evidence_count"] != len(primary["selected"])
                    or additional_context.public_view["evidence_count"] != len(secondary)
                    or secondary_stats["primary_count_unchanged"] != len(primary["selected"])):
                raise RecallBlocked("supplementary_context_count_mismatch")
            if self.cache._current_version() != before:
                self.cache.invalidate()
                raise RecallBlocked("supplementary_source_moved")
            return primary, supplement, {**primary_stats, **secondary_stats}
