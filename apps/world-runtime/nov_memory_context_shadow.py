"""Read-only, identity-bound bridge from verified V2 recall to Nov's Shadow Mode.

Keep exact evidence IDs in process memory only; the persistent shadow receives
only a bounded redacted projection. No proposal, action, plan or world writes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re

from memoria_v2_adapter import CognitiveFrame
from nov_memory_recall_shadow import SCHEMA as RECALL_SCHEMA

SCHEMA = "live-infinita-nov-memory-context-shadow/v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_ADDRESSES = frozenset((
    "need", "region_id", "period", "weather", "target_entity_id", "strategy_id",
))
MAX_EVIDENCE = 8


class MemoryContextRejected(ValueError):
    """No unverifiable source can become cognitive context."""


@dataclass(frozen=True, slots=True)
class MemoryShadowContext:
    frame_id: str
    private_evidence_ids: tuple[str, ...] = field(repr=False)
    public_view: dict[str, Any] = field(repr=False)


def _source_world(frame: CognitiveFrame) -> str:
    matches = [a.removeprefix("live:world:") for a in frame.state_addresses
               if a.startswith("live:world:")]
    if len(matches) != 1 or not matches[0]:
        raise MemoryContextRejected("frame_world_identity")
    if frame.observer_id != "nov":
        raise MemoryContextRejected("observer_not_nov")
    return matches[0]


def freeze_memory_context(frame: CognitiveFrame, recall: dict[str, Any]) -> MemoryShadowContext:
    """Verify the V2 snapshot provenance before carrying its evidence into Shadow."""
    world_id = _source_world(frame)
    if not isinstance(recall, dict) or recall.get("schema") != RECALL_SCHEMA:
        raise MemoryContextRejected("recall_schema")
    if recall.get("mode") != "read-only-shadow" or recall.get("source_backend") != "sqlite-incremental":
        raise MemoryContextRejected("recall_backend")
    for key in ("world_identity_validated", "checkpoint_watermark_in_snapshot"):
        if recall.get(key) is not True:
            raise MemoryContextRejected("unverified_" + key)
    for key in ("selection_authority", "world_mutated", "central_sync", "bdr_used",
                "live_caught_up_claim"):
        if recall.get(key) is not False:
            raise MemoryContextRejected("unsafe_" + key)
    records = recall.get("source_snapshot_records")
    if type(records) is not int or records < 0:
        raise MemoryContextRejected("invalid_snapshot_count")
    selected = recall.get("private_evidence")
    summaries = recall.get("selected")
    if not isinstance(selected, list) or not isinstance(summaries, list):
        raise MemoryContextRejected("private_evidence_required")
    if len(selected) != len(summaries) or len(selected) > MAX_EVIDENCE or len(selected) > records:
        raise MemoryContextRejected("invalid_evidence_count")
    ids: list[str] = []
    seen: set[str] = set()
    overlaps: list[int] = []
    for item, summary in zip(selected, summaries):
        if not isinstance(item, dict) or not isinstance(summary, dict):
            raise MemoryContextRejected("invalid_evidence")
        key, evidence_id, digest = (
            item.get("record_key"), item.get("evidence_id"), item.get("content_sha256")
        )
        if (not isinstance(key, str) or HEX.fullmatch(key) is None
                or not isinstance(digest, str) or HEX.fullmatch(digest) is None
                or evidence_id != "live-obs:" + key[:40]
                or evidence_id in seen):
            raise MemoryContextRejected("evidence_identity")
        if (item.get("provenance") != "live.infinita:npc_episode_v1"
                or item.get("world_id") != world_id):
            raise MemoryContextRejected("evidence_provenance")
        tick = item.get("logical_tick")
        if type(tick) is not int or not 0 <= tick <= frame.tick_id:
            raise MemoryContextRejected("future_or_invalid_evidence_tick")
        if summary.get("logical_tick") != tick or summary.get("source") != "typed_confirmed_nov_outcome":
            raise MemoryContextRejected("summary_provenance")
        address_names = item.get("matching_addresses")
        if (not isinstance(address_names, list) or len(address_names) != len(set(address_names))
                or not set(address_names).issubset(ALLOWED_ADDRESSES)):
            raise MemoryContextRejected("invalid_matching_addresses")
        observation = item.get("observation")
        if not isinstance(observation, dict):
            raise MemoryContextRejected("missing_typed_observation")
        if (summary.get("matched_address_count") != len(address_names)
                or not address_names):
            raise MemoryContextRejected("address_match_inconsistent")
        ids.append(evidence_id)
        seen.add(evidence_id)
        overlaps.append(len(address_names))
    if recall.get("historical_matches", 0) < len(ids):
        raise MemoryContextRejected("match_count_inconsistent")
    public = {
        "schema": SCHEMA,
        "frame_id": frame.frame_id,
        "source": "verified-local-memoria-v2",
        "snapshot_records": records,
        "evidence_count": len(ids),
        "historical_matches": recall["historical_matches"],
        "matched_address_counts": overlaps,
        "checkpoint_unchanged_during_copy": recall.get("checkpoint_unchanged_during_copy") is True,
        "used_to_rank": False,
        "predicts_action": False,
        "world_mutated": False,
        "selection_authority": False,
        "central_sync": False,
        "bdr_used": False,
        "live_caught_up_claim": False,
    }
    return MemoryShadowContext(frame.frame_id, tuple(ids), public)
