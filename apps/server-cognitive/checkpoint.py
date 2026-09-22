from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Any

from memoria_resolutiva.intervention_consequence_v2 import InterventionConsequenceMemory
from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionStateMemory,
)
from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservation,
    StructuralTemporalObservationMemory,
)

from nov_need_scheduler import NeedState
from server_cognitive_rc1_checkpoint import (
    _admission_snapshot_from_dict,
    _admission_snapshot_to_dict,
    _context_observation_from_dict,
    _context_observation_to_dict,
    _decode_value,
    _encode_value,
    _episode_from_dict,
    _episode_to_dict,
    _higher_from_dict,
    _higher_to_dict,
    _pairwise_from_dict,
    _pairwise_to_dict,
    _reorder_from_dict,
    _reorder_to_dict,
    _situated_regimes_from_list,
    _situated_regimes_to_list,
)


CHECKPOINT_FORMAT = "live.infinita/apps-server-cognitive-rc1"
CHECKPOINT_VERSION = 1


def _temporal_observation_to_dict(item: StructuralTemporalObservation):
    return {
        "observation_id": item.observation_id,
        "pattern_a": item.pattern_a,
        "pattern_b": item.pattern_b,
        "orientation": item.orientation,
        "source_candidate_id": item.source_candidate_id,
        "rho": item.rho,
        "selectivity": item.selectivity,
        "temporal_stability": item.temporal_stability,
        "evidence_score": item.evidence_score,
        "orientation_confidence": item.orientation_confidence,
        "mean_dt": item.mean_dt,
        "variance_dt": item.variance_dt,
        "supporting_slice_ids": list(item.supporting_slice_ids),
        "supporting_frame_ids": list(item.supporting_frame_ids),
        "provenance": item.provenance,
    }


def _temporal_observation_from_dict(raw):
    return StructuralTemporalObservation(
        observation_id=str(raw["observation_id"]),
        pattern_a=str(raw["pattern_a"]),
        pattern_b=str(raw["pattern_b"]),
        orientation=str(raw["orientation"]),
        source_candidate_id=str(raw["source_candidate_id"]),
        rho=float(raw["rho"]),
        selectivity=float(raw["selectivity"]),
        temporal_stability=float(raw["temporal_stability"]),
        evidence_score=float(raw["evidence_score"]),
        orientation_confidence=float(raw["orientation_confidence"]),
        mean_dt=float(raw["mean_dt"]),
        variance_dt=float(raw["variance_dt"]),
        supporting_slice_ids=tuple(raw["supporting_slice_ids"]),
        supporting_frame_ids=tuple(raw["supporting_frame_ids"]),
        provenance=str(raw.get("provenance") or ""),
    )


def engine_checkpoint(engine) -> dict[str, Any]:
    return {
        "format": CHECKPOINT_FORMAT,
        "version": CHECKPOINT_VERSION,
        "engine": {
            "observer_id": engine.observer_id,
            "world": _encode_value(engine.world),
            "needs": {
                "tick_id": engine.needs.tick_id,
                "pressures": [list(x) for x in engine.needs.pressures],
            },
            "cycle_id": engine.cycle_id,
            "simulation_time": engine.simulation_time,
            "provenance_by_slice": [
                [int(key), list(value)]
                for key, value in sorted(engine.provenance_by_slice.items())
            ],
            "activity_limit": engine.activity.maxlen,
            "activity": _encode_value(list(engine.activity)),
            "rejections": _encode_value(list(engine.rejections)),
            "last_decision": _encode_value(engine.last_decision),
        },
        "causal_memory": [
            _episode_to_dict(x)
            for x in engine.gym.memory.snapshot()
        ],
        "situated_regimes": _situated_regimes_to_list(engine.gym.regimes),
        "temporal_memory": [
            _temporal_observation_to_dict(x)
            for x in engine.temporal_memory.snapshot()
        ],
        "context_memory": [
            _context_observation_to_dict(x)
            for x in engine.context_memory.snapshot()
        ],
        "admission_memory": [
            _admission_snapshot_to_dict(x)
            for x in engine.admission_memory.snapshot()
        ],
        "pairwise": _pairwise_to_dict(engine.pairwise),
        "higher": _higher_to_dict(engine.higher),
        "reorder": _reorder_to_dict(engine.reorder),
    }


def restore_engine_from_checkpoint(raw: dict[str, Any]):
    if raw.get("format") != CHECKPOINT_FORMAT:
        raise ValueError("unsupported server cognitive checkpoint format")
    if int(raw.get("version") or 0) != CHECKPOINT_VERSION:
        raise ValueError("unsupported server cognitive checkpoint version")

    from engine import ServerCognitiveEngine

    state = raw["engine"]
    engine = ServerCognitiveEngine(
        episode_id=1,
        observer_id=str(state["observer_id"]),
        activity_limit=int(state.get("activity_limit") or 500),
    )

    needs = state["needs"]
    engine.world = _decode_value(state["world"])
    engine.needs = NeedState(
        tick_id=int(needs["tick_id"]),
        pressures=tuple(
            (str(key), int(value))
            for key, value in needs["pressures"]
        ),
    )

    causal = InterventionConsequenceMemory.restore(
        tuple(
            _episode_from_dict(x)
            for x in raw.get("causal_memory") or ()
        )
    )
    regimes = _situated_regimes_from_list(
        raw.get("situated_regimes") or ()
    )
    engine.gym = SituatedLiveCognitiveGymV2(
        memory=causal,
        min_independent_episodes=2,
        min_contiguous_support=2,
        regimes=regimes,
    )

    engine.temporal_memory = StructuralTemporalObservationMemory.restore(
        tuple(
            _temporal_observation_from_dict(x)
            for x in raw.get("temporal_memory") or ()
        )
    )
    engine.context_memory = StructuralContextObservationMemory.restore(
        tuple(
            _context_observation_from_dict(x)
            for x in raw.get("context_memory") or ()
        )
    )
    engine.admission_memory = StructuralContextAdmissionStateMemory.restore(
        tuple(
            _admission_snapshot_from_dict(x)
            for x in raw.get("admission_memory") or ()
        )
    )

    engine.pairwise = _pairwise_from_dict(raw["pairwise"])
    engine.higher = _higher_from_dict(raw["higher"])
    engine.reorder = _reorder_from_dict(raw["reorder"])
    engine.higher_policy = __import__(
        "higher_order_context_selector"
    ).policy_from_world(engine.world)

    engine.provenance_by_slice = {
        int(key): tuple(value)
        for key, value in state.get("provenance_by_slice") or ()
    }
    engine.cycle_id = int(state["cycle_id"])
    engine.simulation_time = float(state["simulation_time"])
    engine.activity = deque(
        _decode_value(state.get("activity") or {
            "__kind__": "list",
            "items": [],
        }),
        maxlen=int(state.get("activity_limit") or 500),
    )
    engine.rejections = deque(
        _decode_value(state.get("rejections") or {
            "__kind__": "list",
            "items": [],
        }),
        maxlen=int(state.get("activity_limit") or 500),
    )
    engine.last_decision = _decode_value(
        state.get("last_decision")
    )
    engine.last_causal_step = None
    return engine


def save_engine_checkpoint(engine, path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    payload = engine_checkpoint(engine)
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target


def load_engine_checkpoint(path: str | os.PathLike[str]):
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return restore_engine_from_checkpoint(raw)
