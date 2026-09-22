from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from memoria_resolutiva.contextual_temporal_regime_v2 import ContextualRegimeKey
from memoria_resolutiva.intervention_consequence_v2 import (
    InterventionConsequenceMemory,
    InterventionEpisode,
)
from memoria_resolutiva.situated_contextual_regime_v2 import (
    SituatedContextKey,
    SituatedContextualRegimes,
)
from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionSnapshot,
    StructuralContextAdmissionStateMemory,
)
from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservation,
    StructuralContextObservationMemory,
)
from memoria_resolutiva.temporal_regime_state_v2 import (
    TemporalOutcomeKey,
    TemporalRegimeState,
)
from reality_slice import (
    Association,
    ContextAssociation,
    Modality,
    Occurrence,
    RealitySlice,
    RealitySliceReorderBuffer,
    SparseContextAssociator,
    TemporalAssociator,
)

from nov_need_scheduler import NeedState


CHECKPOINT_FORMAT = "live.infinita/server-cognitive-rc1"
CHECKPOINT_VERSION = 1


def _encode_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"__kind__": "tuple", "items": [_encode_value(x) for x in value]}
    if isinstance(value, set):
        return {
            "__kind__": "set",
            "items": [_encode_value(x) for x in sorted(value, key=repr)],
        }
    if isinstance(value, dict):
        return {
            "__kind__": "dict",
            "items": [
                [_encode_value(key), _encode_value(item)]
                for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
            ],
        }
    if isinstance(value, list):
        return {"__kind__": "list", "items": [_encode_value(x) for x in value]}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported checkpoint value: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or "__kind__" not in value:
        return value
    kind = value["__kind__"]
    items = value.get("items") or []
    if kind == "tuple":
        return tuple(_decode_value(x) for x in items)
    if kind == "set":
        return set(_decode_value(x) for x in items)
    if kind == "list":
        return [_decode_value(x) for x in items]
    if kind == "dict":
        return {
            _decode_value(pair[0]): _decode_value(pair[1])
            for pair in items
        }
    raise ValueError(f"unknown checkpoint encoded kind: {kind}")


def _temporal_outcome_to_dict(value: TemporalOutcomeKey | None):
    if value is None:
        return None
    return {
        "consequence_addresses": list(value.consequence_addresses),
        "next_state_addresses": list(value.next_state_addresses),
    }


def _temporal_outcome_from_dict(value):
    if value is None:
        return None
    return TemporalOutcomeKey(
        consequence_addresses=tuple(value["consequence_addresses"]),
        next_state_addresses=tuple(value["next_state_addresses"]),
    )


def _regime_state_to_dict(state: TemporalRegimeState) -> dict[str, Any]:
    return {
        "active": _temporal_outcome_to_dict(state.active),
        "pending": _temporal_outcome_to_dict(state.pending),
        "pending_count": state.pending_count,
        "active_run": state.active_run,
        "generation": state.generation,
        "switches": state.switches,
        "observations": state.observations,
    }


def _regime_state_from_dict(raw: dict[str, Any]) -> TemporalRegimeState:
    return TemporalRegimeState(
        active=_temporal_outcome_from_dict(raw.get("active")),
        pending=_temporal_outcome_from_dict(raw.get("pending")),
        pending_count=int(raw["pending_count"]),
        active_run=int(raw["active_run"]),
        generation=int(raw["generation"]),
        switches=int(raw["switches"]),
        observations=int(raw["observations"]),
    )


def _situated_regimes_to_list(regimes: SituatedContextualRegimes):
    output = []
    for key, state in regimes.entries:
        output.append(
            {
                "key": {
                    "structural_key": {
                        "state_width": key.structural_key.state_width,
                        "state_equality_pattern": list(
                            key.structural_key.state_equality_pattern
                        ),
                        "intervention_role": key.structural_key.intervention_role,
                    },
                    "state_signature": list(key.state_signature),
                    "intervention_address": key.intervention_address,
                },
                "state": _regime_state_to_dict(state),
            }
        )
    return output


def _situated_regimes_from_list(values) -> SituatedContextualRegimes:
    entries = []
    for item in values:
        raw_key = item["key"]
        raw_structural = raw_key["structural_key"]
        structural = ContextualRegimeKey(
            state_width=int(raw_structural["state_width"]),
            state_equality_pattern=tuple(
                int(x) for x in raw_structural["state_equality_pattern"]
            ),
            intervention_role=str(raw_structural["intervention_role"]),
        )
        key = SituatedContextKey(
            structural_key=structural,
            state_signature=tuple(raw_key["state_signature"]),
            intervention_address=str(raw_key["intervention_address"]),
        )
        entries.append((key, _regime_state_from_dict(item["state"])))
    return SituatedContextualRegimes(tuple(entries))


def _episode_to_dict(item: InterventionEpisode) -> dict[str, Any]:
    return {
        "episode_id": item.episode_id,
        "state_addresses": list(item.state_addresses),
        "intervention_address": item.intervention_address,
        "consequence_addresses": list(item.consequence_addresses),
        "next_state_addresses": list(item.next_state_addresses),
        "provenance": item.provenance,
    }


def _episode_from_dict(raw: dict[str, Any]) -> InterventionEpisode:
    return InterventionEpisode(
        episode_id=str(raw["episode_id"]),
        state_addresses=tuple(raw["state_addresses"]),
        intervention_address=str(raw["intervention_address"]),
        consequence_addresses=tuple(raw["consequence_addresses"]),
        next_state_addresses=tuple(raw["next_state_addresses"]),
        provenance=str(raw.get("provenance") or ""),
    )


def _context_observation_to_dict(item: StructuralContextObservation):
    return {
        "observation_id": item.observation_id,
        "antecedent_patterns": list(item.antecedent_patterns),
        "consequence_pattern": item.consequence_pattern,
        "source_candidate_id": item.source_candidate_id,
        "rho": item.rho,
        "context_coverage": item.context_coverage,
        "temporal_stability": item.temporal_stability,
        "context_reliability": item.context_reliability,
        "lower_order_reliabilities": list(item.lower_order_reliabilities),
        "repetitions": item.repetitions,
        "mean_delay": item.mean_delay,
        "variance_delay": item.variance_delay,
        "supporting_slice_ids": list(item.supporting_slice_ids),
        "supporting_frame_ids": list(item.supporting_frame_ids),
        "provenance": item.provenance,
    }


def _context_observation_from_dict(raw):
    return StructuralContextObservation(
        observation_id=str(raw["observation_id"]),
        antecedent_patterns=tuple(raw["antecedent_patterns"]),
        consequence_pattern=str(raw["consequence_pattern"]),
        source_candidate_id=str(raw["source_candidate_id"]),
        rho=float(raw["rho"]),
        context_coverage=float(raw["context_coverage"]),
        temporal_stability=float(raw["temporal_stability"]),
        context_reliability=float(raw["context_reliability"]),
        lower_order_reliabilities=tuple(
            float(x) for x in raw["lower_order_reliabilities"]
        ),
        repetitions=int(raw["repetitions"]),
        mean_delay=float(raw["mean_delay"]),
        variance_delay=float(raw["variance_delay"]),
        supporting_slice_ids=tuple(raw["supporting_slice_ids"]),
        supporting_frame_ids=tuple(raw["supporting_frame_ids"]),
        provenance=str(raw.get("provenance") or ""),
    )


def _admission_snapshot_to_dict(item: StructuralContextAdmissionSnapshot):
    return {
        "snapshot_id": item.snapshot_id,
        "antecedent_patterns": list(item.antecedent_patterns),
        "active_candidate_ids": list(item.active_candidate_ids),
        "source_epoch_id": item.source_epoch_id,
        "supporting_slice_ids": list(item.supporting_slice_ids),
        "provenance": item.provenance,
        "resolution_state": item.resolution_state,
        "competing_candidate_ids": list(item.competing_candidate_ids),
    }


def _admission_snapshot_from_dict(raw):
    return StructuralContextAdmissionSnapshot(
        snapshot_id=str(raw["snapshot_id"]),
        antecedent_patterns=tuple(raw["antecedent_patterns"]),
        active_candidate_ids=tuple(raw["active_candidate_ids"]),
        source_epoch_id=str(raw["source_epoch_id"]),
        supporting_slice_ids=tuple(raw["supporting_slice_ids"]),
        provenance=str(raw.get("provenance") or ""),
        resolution_state=str(raw.get("resolution_state") or "unsupported"),
        competing_candidate_ids=tuple(raw.get("competing_candidate_ids") or ()),
    )


def _pairwise_to_dict(pairwise: TemporalAssociator) -> dict[str, Any]:
    links = []
    for key, link in sorted(pairwise.links.items()):
        links.append(
            {
                "key": list(key),
                "a": link.a,
                "b": link.b,
                "rho": link.rho,
                "forward": link.forward,
                "simultaneous": link.simultaneous,
                "backward": link.backward,
                "repetitions": link.repetitions,
                "mean_dt": link.mean_dt,
                "m2_dt": link.m2_dt,
                "last_time": link.last_time,
                "seen_slices": sorted(link.seen_slices),
            }
        )
    return {
        "config": {
            "eta": pairwise.eta,
            "lambda0": pairwise.lambda0,
            "consolidation": pairwise.consolidation,
            "simultaneous_delta": pairwise.simultaneous_delta,
            "min_proximity": pairwise.min_proximity,
            "default_tau": pairwise.default_tau,
        },
        "total_slices": pairwise.total_slices,
        "pattern_slices": [
            [int(key), int(value)]
            for key, value in sorted(pairwise.pattern_slices.items())
        ],
        "links": links,
    }


def _pairwise_from_dict(raw) -> TemporalAssociator:
    config = raw["config"]
    value = TemporalAssociator(
        eta=float(config["eta"]),
        lambda0=float(config["lambda0"]),
        consolidation=float(config["consolidation"]),
        simultaneous_delta=float(config["simultaneous_delta"]),
        min_proximity=float(config["min_proximity"]),
        default_tau=float(config["default_tau"]),
    )
    value.total_slices = int(raw["total_slices"])
    value.pattern_slices = {
        int(key): int(count)
        for key, count in raw.get("pattern_slices") or ()
    }
    for item in raw.get("links") or ():
        key = tuple(int(x) for x in item["key"])
        value.links[key] = Association(
            a=int(item["a"]),
            b=int(item["b"]),
            rho=float(item["rho"]),
            forward=float(item["forward"]),
            simultaneous=float(item["simultaneous"]),
            backward=float(item["backward"]),
            repetitions=int(item["repetitions"]),
            mean_dt=float(item["mean_dt"]),
            m2_dt=float(item["m2_dt"]),
            last_time=float(item["last_time"]),
            seen_slices=set(int(x) for x in item["seen_slices"]),
        )
    return value


def _higher_to_dict(higher: SparseContextAssociator) -> dict[str, Any]:
    links = []
    for key, link in sorted(higher.links.items()):
        links.append(
            {
                "key": list(key),
                "antecedents": list(link.antecedents),
                "consequence": link.consequence,
                "rho": link.rho,
                "repetitions": link.repetitions,
                "mean_delay": link.mean_delay,
                "m2_delay": link.m2_delay,
                "last_time": link.last_time,
                "last_decay_time": link.last_decay_time,
                "seen_slices": sorted(link.seen_slices),
            }
        )
    return {
        "config": {
            "eta": higher.eta,
            "lambda0": higher.lambda0,
            "consolidation": higher.consolidation,
            "simultaneous_delta": higher.simultaneous_delta,
            "context_span": higher.context_span,
            "max_consequence_delay": higher.max_consequence_delay,
            "min_pattern_support": higher.min_pattern_support,
        },
        "total_slices": higher.total_slices,
        "context_slices": [
            [list(key), int(value)]
            for key, value in sorted(higher.context_slices.items())
        ],
        "context_seen_slices": [
            [list(key), sorted(value)]
            for key, value in sorted(higher.context_seen_slices.items())
        ],
        "slice_end_times": [
            [int(key), float(value)]
            for key, value in sorted(higher.slice_end_times.items())
        ],
        "links": links,
    }


def _higher_from_dict(raw) -> SparseContextAssociator:
    config = raw["config"]
    value = SparseContextAssociator(
        eta=float(config["eta"]),
        lambda0=float(config["lambda0"]),
        consolidation=float(config["consolidation"]),
        simultaneous_delta=float(config["simultaneous_delta"]),
        context_span=float(config["context_span"]),
        max_consequence_delay=float(config["max_consequence_delay"]),
        min_pattern_support=int(config["min_pattern_support"]),
    )
    value.total_slices = int(raw["total_slices"])
    value.context_slices = {
        tuple(int(x) for x in key): int(count)
        for key, count in raw.get("context_slices") or ()
    }
    value.context_seen_slices = {
        tuple(int(x) for x in key): set(int(x) for x in slices)
        for key, slices in raw.get("context_seen_slices") or ()
    }
    value.slice_end_times = {
        int(key): float(end_time)
        for key, end_time in raw.get("slice_end_times") or ()
    }
    for item in raw.get("links") or ():
        key = tuple(int(x) for x in item["key"])
        value.links[key] = ContextAssociation(
            antecedents=tuple(int(x) for x in item["antecedents"]),
            consequence=int(item["consequence"]),
            rho=float(item["rho"]),
            repetitions=int(item["repetitions"]),
            mean_delay=float(item["mean_delay"]),
            m2_delay=float(item["m2_delay"]),
            last_time=float(item["last_time"]),
            last_decay_time=float(item["last_decay_time"]),
            seen_slices=set(int(x) for x in item["seen_slices"]),
        )
    return value


def _occurrence_to_dict(item: Occurrence):
    return {
        "pattern": item.pattern,
        "modality": int(item.modality),
        "t_start": item.t_start,
        "t_end": item.t_end,
        "source": item.source,
        "provenance": item.provenance,
    }


def _occurrence_from_dict(raw):
    return Occurrence(
        pattern=int(raw["pattern"]),
        modality=Modality(int(raw["modality"])),
        t_start=float(raw["t_start"]),
        t_end=float(raw["t_end"]),
        source=int(raw["source"]),
        provenance=int(raw["provenance"]),
    )


def _reality_slice_to_dict(item: RealitySlice):
    return {
        "slice_id": item.slice_id,
        "t_start": item.t_start,
        "t_end": item.t_end,
        "occurrences": [_occurrence_to_dict(x) for x in item.occurrences],
        "provenance": list(item.provenance),
    }


def _reality_slice_from_dict(raw):
    return RealitySlice(
        slice_id=int(raw["slice_id"]),
        t_start=float(raw["t_start"]),
        t_end=float(raw["t_end"]),
        occurrences=tuple(
            _occurrence_from_dict(x)
            for x in raw.get("occurrences") or ()
        ),
        provenance=tuple(int(x) for x in raw.get("provenance") or ()),
    )


def _reorder_to_dict(reorder: RealitySliceReorderBuffer):
    return {
        "allowed_lateness": reorder.allowed_lateness,
        "max_event_time": reorder.max_event_time,
        "watermark": reorder.watermark,
        "pending": [
            _reality_slice_to_dict(item)
            for item in sorted(
                reorder._pending.values(),
                key=reorder._order_key,
            )
        ],
        "seen_slice_ids": sorted(reorder._seen_slice_ids),
    }


def _reorder_from_dict(raw):
    value = RealitySliceReorderBuffer(
        allowed_lateness=float(raw["allowed_lateness"])
    )
    value.max_event_time = (
        None
        if raw.get("max_event_time") is None
        else float(raw["max_event_time"])
    )
    value.watermark = (
        None
        if raw.get("watermark") is None
        else float(raw["watermark"])
    )
    value._pending = {
        int(item.slice_id): item
        for item in (
            _reality_slice_from_dict(raw_item)
            for raw_item in raw.get("pending") or ()
        )
    }
    value._seen_slice_ids = set(
        int(x) for x in raw.get("seen_slice_ids") or ()
    )
    return value


def runtime_checkpoint(runtime) -> dict[str, Any]:
    return {
        "format": CHECKPOINT_FORMAT,
        "version": CHECKPOINT_VERSION,
        "runtime": {
            "world": _encode_value(runtime.world),
            "needs": {
                "tick_id": runtime.needs.tick_id,
                "pressures": [list(x) for x in runtime.needs.pressures],
            },
            "cycles": runtime.cycles,
            "simulation_time": runtime.simulation_time,
            "reality_slices_offered": runtime.reality_slices_offered,
            "reality_slices_ingested": runtime.reality_slices_ingested,
            "late_rejection_count": runtime.late_rejection_count,
            "recent_late_rejections": _encode_value(
                runtime.recent_late_rejections
            ),
            "provenance_by_slice": [
                [int(key), list(value)]
                for key, value in sorted(runtime.provenance_by_slice.items())
            ],
            "last_window_id": runtime.last_window_id,
            "last_ingested_slice_ids": list(runtime.last_ingested_slice_ids),
        },
        "causal_memory": [
            _episode_to_dict(x)
            for x in runtime.gym.memory.snapshot()
        ],
        "situated_regimes": _situated_regimes_to_list(runtime.gym.regimes),
        "pairwise": _pairwise_to_dict(runtime.pairwise),
        "higher": _higher_to_dict(runtime.higher),
        "reorder": _reorder_to_dict(runtime.reorder),
        "context_memory": [
            _context_observation_to_dict(x)
            for x in runtime.context_memory.snapshot()
        ],
        "admission_memory": [
            _admission_snapshot_to_dict(x)
            for x in runtime.admission_memory.snapshot()
        ],
    }


def restore_runtime_from_checkpoint(raw: dict[str, Any]):
    if raw.get("format") != CHECKPOINT_FORMAT:
        raise ValueError("unsupported checkpoint format")
    if int(raw.get("version") or 0) != CHECKPOINT_VERSION:
        raise ValueError("unsupported checkpoint version")

    from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
    from server_cognitive_rc1_runtime import ServerCognitiveRC1Runtime

    state = raw["runtime"]
    needs_raw = state["needs"]

    causal = InterventionConsequenceMemory.restore(
        tuple(_episode_from_dict(x) for x in raw.get("causal_memory") or ())
    )
    regimes = _situated_regimes_from_list(raw.get("situated_regimes") or ())
    gym = SituatedLiveCognitiveGymV2(
        memory=causal,
        min_independent_episodes=2,
        min_contiguous_support=2,
        regimes=regimes,
    )

    runtime = ServerCognitiveRC1Runtime(
        world=_decode_value(state["world"]),
        needs=NeedState(
            tick_id=int(needs_raw["tick_id"]),
            pressures=tuple(
                (str(key), int(value))
                for key, value in needs_raw["pressures"]
            ),
        ),
        gym=gym,
        pairwise=_pairwise_from_dict(raw["pairwise"]),
        higher=_higher_from_dict(raw["higher"]),
        reorder=_reorder_from_dict(raw["reorder"]),
        context_memory=StructuralContextObservationMemory.restore(
            tuple(
                _context_observation_from_dict(x)
                for x in raw.get("context_memory") or ()
            )
        ),
        admission_memory=StructuralContextAdmissionStateMemory.restore(
            tuple(
                _admission_snapshot_from_dict(x)
                for x in raw.get("admission_memory") or ()
            )
        ),
        provenance_by_slice={
            int(key): tuple(value)
            for key, value in state.get("provenance_by_slice") or ()
        },
        cycles=int(state["cycles"]),
        simulation_time=float(state["simulation_time"]),
        reality_slices_offered=int(state["reality_slices_offered"]),
        reality_slices_ingested=int(state["reality_slices_ingested"]),
        late_rejection_count=int(state["late_rejection_count"]),
        recent_late_rejections=_decode_value(
            state.get("recent_late_rejections") or {
                "__kind__": "list",
                "items": [],
            }
        ),
        last_window_id=(
            None
            if state.get("last_window_id") is None
            else int(state["last_window_id"])
        ),
        last_ingested_slice_ids=tuple(
            int(x) for x in state.get("last_ingested_slice_ids") or ()
        ),
    )
    return runtime


def save_runtime_checkpoint(runtime, path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = runtime_checkpoint(runtime)
    temporary = target.with_name(f".{target.name}.tmp")
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


def load_runtime_checkpoint(path: str | os.PathLike[str]):
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return restore_runtime_from_checkpoint(raw)
