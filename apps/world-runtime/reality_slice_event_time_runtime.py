from __future__ import annotations

from dataclasses import dataclass

from reality_slice import (
    RealitySlice,
    RealitySliceReorderBatch,
    RealitySliceReorderBuffer,
    SparseContextAssociator,
    TemporalAssociator,
)


@dataclass(frozen=True, slots=True)
class EventTimeIngestResult:
    batch: RealitySliceReorderBatch
    ingested_slice_ids: tuple[int, ...]


def _ingest_emitted(
    emitted: tuple[RealitySlice, ...],
    *,
    pairwise: TemporalAssociator,
    higher: SparseContextAssociator,
) -> tuple[int, ...]:
    ingested: list[int] = []
    for reality_slice in emitted:
        pairwise.ingest(reality_slice)
        higher.ingest(
            reality_slice,
            pattern_support=pairwise.pattern_slices,
        )
        ingested.append(int(reality_slice.slice_id))
    return tuple(ingested)


def ingest_reality_slice_event_time(
    reorder: RealitySliceReorderBuffer,
    pairwise: TemporalAssociator,
    higher: SparseContextAssociator,
    reality_slice: RealitySlice,
) -> EventTimeIngestResult:
    """Offer one arrived slice and ingest only event-time-safe emitted slices."""
    batch = reorder.offer(reality_slice)
    return EventTimeIngestResult(
        batch=batch,
        ingested_slice_ids=_ingest_emitted(
            batch.emitted,
            pairwise=pairwise,
            higher=higher,
        ),
    )


def flush_reality_slice_event_time(
    reorder: RealitySliceReorderBuffer,
    pairwise: TemporalAssociator,
    higher: SparseContextAssociator,
) -> EventTimeIngestResult:
    """Flush accepted pending slices in deterministic event-time order."""
    batch = reorder.flush()
    return EventTimeIngestResult(
        batch=batch,
        ingested_slice_ids=_ingest_emitted(
            batch.emitted,
            pairwise=pairwise,
            higher=higher,
        ),
    )
