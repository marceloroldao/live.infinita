from __future__ import annotations

from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservation,
    StructuralTemporalObservationMemory,
)

from temporal_evidence_selector import TemporalEvidenceCandidate


def ingest_temporal_evidence_candidate(
    memory: StructuralTemporalObservationMemory,
    candidate: TemporalEvidenceCandidate,
    *,
    provenance: str = "live.infinita/bit.analyze",
) -> StructuralTemporalObservation:
    """Bridge one admitted presemantic candidate into Memoria.ia V2 observation memory.

    This adapter does not create an intervention, causal predicate, semantic label, or
    fact. It preserves only opaque pattern addresses, temporal orientation, evidence
    metrics and independent provenance already admitted by the upstream selector.
    """
    return memory.ingest_observation(
        pattern_a=f"temporal:pattern:{candidate.pattern_a}",
        pattern_b=f"temporal:pattern:{candidate.pattern_b}",
        orientation=candidate.orientation,
        source_candidate_id=candidate.candidate_id,
        rho=candidate.rho,
        selectivity=candidate.selectivity,
        temporal_stability=candidate.temporal_stability,
        evidence_score=candidate.evidence_score,
        orientation_confidence=candidate.orientation_confidence,
        mean_dt=candidate.mean_dt,
        variance_dt=candidate.variance_dt,
        supporting_slice_ids=tuple(str(item) for item in candidate.supporting_slice_ids),
        supporting_frame_ids=candidate.supporting_frame_ids,
        provenance=provenance,
    )
