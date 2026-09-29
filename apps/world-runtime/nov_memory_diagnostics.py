"""MVP-018G: owner-only read-only diagnostics on real Nov memory.

Produces aggregate performance and address-diversity counts only. The frame is
retrospective, based on the last confirmed episode, not Nov's live agent state.
Nothing is written to the original database, checkpoint or World State.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import resource
import sqlite3
import statistics
from time import perf_counter_ns
from typing import Any

from memoria_v2_adapter import CognitiveFrame
from nov_memory_context_shadow import MemoryContextRejected, freeze_memory_context
from nov_memory_recall_cache import VersionedNovRecallCache
from nov_memory_recall_shadow import (
    FIELDS, MAX_WORLD_BYTES, RecallBlocked, _read_bounded_json, recall_once,
)

SCHEMA = "live-infinita-nov-recall-diagnostics/v1"


def retrospective_frame(world: dict[str, Any], records: list[dict[str, Any]]) -> CognitiveFrame:
    world_id = world.get("world_id")
    if not isinstance(world_id, str) or not world_id:
        raise RecallBlocked("world_identity_missing")
    seed = max(records, key=lambda r: (r["logical_tick"], r["record_key"])) if records else None
    tick_value = world.get("current_tick", world.get("sequence", 0))
    current_tick = tick_value if type(tick_value) is int and tick_value >= 0 else 0
    tick = max(current_tick, seed["logical_tick"] if seed else 0)
    addresses = ["live:world:" + world_id, "live:entity:nov"]
    if seed and seed["addresses"].get("region_id"):
        addresses.append("live:region:" + seed["addresses"]["region_id"])
    environment = world.get("environment")
    if isinstance(environment, dict):
        for key in ("period", "weather"):
            value = environment.get(key)
            if isinstance(value, str) and value:
                addresses.append("live:" + key + ":" + value)
    digest = sha256((world_id + "|" + str(tick)).encode("utf-8")).hexdigest()[:24]
    return CognitiveFrame(
        frame_id="diagnostic_" + digest, tick_id=tick, observer_id="nov",
        state_addresses=tuple(addresses), available_interventions=(),
        candidate_outcomes=(), provenance={"authority": "read-only-retrospective"},
    )


def diversity(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = {
        name: len({
            row["addresses"][name] for row in records
            if isinstance(row["addresses"].get(name), str)
        })
        for name in FIELDS
    }
    signatures = Counter(
        tuple(sorted(row["addresses"].items())) for row in records
    )
    return {
        "distinct_address_values": values,
        "distinct_episode_signatures": len(signatures),
        "largest_identical_signature_group": max(signatures.values(), default=0),
    }


def diagnose(
    *, source: Path, checkpoint: Path, world: Path, private_root: Path,
    samples: int = 20,
) -> dict[str, Any]:
    if type(samples) is not int or not 1 <= samples <= 30:
        raise RecallBlocked("invalid_sample_count")
    cache = VersionedNovRecallCache(
        source=source, checkpoint_path=checkpoint,
        world_path=world, private_root=private_root,
    )
    version = cache._current_version()
    initial = recall_once(
        source=source, checkpoint_path=checkpoint, world_path=world,
        private_root=private_root, include_index=True,
    )
    rows = initial.pop("_private_index", None)
    if (not isinstance(rows, list)
            or initial.get("checkpoint_unchanged_during_copy") is not True
            or initial.get("world_identity_validated") is not True
            or initial.get("checkpoint_watermark_in_snapshot") is not True
            or initial.get("world_mutated") is not False
            or initial.get("selection_authority") is not False
            or initial.get("bdr_used") is not False
            or initial.get("central_sync") is not False
            or len(rows) != initial.get("nov_observations")):
        raise RecallBlocked("initial_snapshot_invalid")
    _, world_doc = _read_bounded_json(world, MAX_WORLD_BYTES, "world")
    frame = retrospective_frame(world_doc, rows)
    patterns = diversity(rows)
    del rows
    if cache._current_version() != version:
        raise RecallBlocked("source_changed_between_probes")
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = perf_counter_ns()
    first = cache(frame)
    cold_ms = (perf_counter_ns() - started) / 1_000_000
    if (first.get("cache_status") != "refreshed"
            or first["source_snapshot_records"] != initial["source_snapshot_records"]
            or first["nov_observations"] != initial["nov_observations"]):
        raise RecallBlocked("cache_proof_disagrees")
    memory_context = freeze_memory_context(frame, first)
    warm: list[float] = []
    for _ in range(samples):
        started = perf_counter_ns()
        value = cache(frame)
        elapsed = (perf_counter_ns() - started) / 1_000_000
        if value.get("cache_status") != "hit" or value.get("selected") != first.get("selected"):
            raise RecallBlocked("cache_not_reused_or_inconsistent")
        warm.append(elapsed)
    if cache._current_version() != version:
        raise RecallBlocked("source_changed_during_benchmark")
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "schema": SCHEMA,
        "status": "ok",
        "mode": "read-only-retrospective",
        "snapshot_records": first["source_snapshot_records"],
        "nov_observations": first["nov_observations"],
        "historical_matches": first["historical_matches"],
        "retrieved_evidence_count": memory_context.public_view["evidence_count"],
        "query_address_count": first["query_address_count"],
        "matched_address_counts": memory_context.public_view["matched_address_counts"],
        **patterns,
        "cold_validation_ms": round(cold_ms, 3),
        "warm_median_ms": round(statistics.median(warm), 3),
        "warm_max_ms": round(max(warm), 3),
        "warm_queries": samples,
        "peak_rss_kib": peak_rss,
        "rss_peak_delta_kib": max(0, peak_rss - baseline_rss),
        "checkpoint_stable": True,
        "world_mutated": False,
        "selection_authority": False,
        "central_sync": False,
        "bdr_used": False,
        "live_caught_up_claim": False,
        "live_nov_state_measured": False,
    }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    try:
        output = diagnose(
            source=args.source, checkpoint=args.checkpoint, world=args.world,
            private_root=args.private_root, samples=args.samples,
        )
    except (RecallBlocked, MemoryContextRejected) as exc:
        raise SystemExit("MVP018G_NOV_DIAGNOSTICS_BLOCKED " + str(exc)) from exc
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, RuntimeError) as exc:
        raise SystemExit("MVP018G_NOV_DIAGNOSTICS_BLOCKED validation_failed") from exc
    print("MVP018G_NOV_DIAGNOSTICS_OK " +
          json.dumps(output, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
