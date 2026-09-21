from __future__ import annotations

from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionStateMemory,
)

from higher_order_context_selector import HigherOrderContextCandidate


def ingest_higher_order_context_candidate(
    memory: StructuralContextObservationMemory,
    candidate: HigherOrderContextCandidate,
):
    """Store one admitted opaque higher-order candidate in Memoria.ia V2."""
    return memory.ingest_observation(
        antecedent_patterns=tuple(
            f"temporal:pattern:{value}"
            for value in candidate.antecedent_patterns
        ),
        consequence_pattern=(
            f"temporal:pattern:{candidate.consequence_pattern}"
        ),
        source_candidate_id=candidate.candidate_id,
        rho=candidate.rho,
        context_coverage=candidate.context_coverage,
        temporal_stability=candidate.temporal_stability,
        context_reliability=candidate.context_reliability,
        lower_order_reliabilities=candidate.lower_order_reliabilities,
        repetitions=candidate.repetitions,
        mean_delay=candidate.mean_delay,
        variance_delay=candidate.variance_delay,
        supporting_slice_ids=tuple(
            str(value)
            for value in candidate.supporting_slice_ids
        ),
        supporting_frame_ids=candidate.supporting_frame_ids,
        provenance="live.infinita/bit.analyze:sparse-context",
    )



def refresh_higher_order_context_admission_state(
    memory: StructuralContextAdmissionStateMemory,
    candidates: tuple[HigherOrderContextCandidate, ...],
    *,
    source_epoch_id: str,
    supporting_slice_ids: tuple[int, ...] = (),
):
    """Record the complete current admitted set for known higher-order contexts.

    Contexts that were active previously but have no currently admitted candidate
    receive an explicit empty snapshot. Historical observations remain untouched.
    """
    grouped: dict[tuple[str, str], list[str]] = {}
    for candidate in candidates:
        antecedents = tuple(
            sorted(
                f"temporal:pattern:{value}"
                for value in candidate.antecedent_patterns
            )
        )
        grouped.setdefault(antecedents, []).append(candidate.candidate_id)

    contexts = set(memory.current_contexts()) | set(grouped)
    snapshots = []
    slice_ids = tuple(str(value) for value in supporting_slice_ids)
    for antecedents in sorted(contexts):
        snapshots.append(
            memory.ingest_snapshot(
                antecedent_patterns=antecedents,
                active_candidate_ids=tuple(
                    sorted(grouped.get(antecedents, ()))
                ),
                source_epoch_id=source_epoch_id,
                supporting_slice_ids=slice_ids,
                provenance="live.infinita/bit.analyze:sparse-context-admission",
            )
        )
    return tuple(snapshots)
