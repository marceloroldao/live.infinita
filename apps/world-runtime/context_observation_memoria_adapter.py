from __future__ import annotations

from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
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
