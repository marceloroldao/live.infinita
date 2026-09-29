"""MVP-018L owner-only, read-only live-frame pilot.

The world's cold entity store is single-writer. Never instantiate its mutable
engine/store here: bounded raw reads of world, manifest and Nov's region file
are compared before/after; inconsistent generations ABSTAIN. No IPC yet.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Callable

from memoria_v2_adapter import CognitiveFrame, build_nov_cognitive_frame
from nov_memory_async_prepare import OwnerAsyncDualLanePreparation
from nov_memory_recall_cache import VersionedNovRecallCache
from nov_memory_recall_shadow import MAX_WORLD_BYTES, RecallBlocked, _read_bounded_json

SCHEMA = "live-infinita-nov-owner-live-frame-pilot/v1"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_REGION_BYTES = 4 * 1024 * 1024
MAX_CYCLES = 60
MIN_INTERVAL = 0.5
MAX_INTERVAL = 3.0
ALLOWED_STATUS = frozenset((
    "ready", "not_ready", "pending", "blocked", "source_changed", "expired",
    "world_changed", "frame_regressed", "frame_lagged", "query_changed",
    "context_rejected", "closed", "not_started", "unavailable",
))


def _bounded_region(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    if path.is_symlink():
        raise RecallBlocked("region_symlink")
    with path.open("rb") as stream:
        raw = stream.read(MAX_REGION_BYTES + 1)
    if len(raw) > MAX_REGION_BYTES:
        raise RecallBlocked("region_oversized")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise RecallBlocked("region_invalid") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise RecallBlocked("region_invalid")
    return raw, value


def read_current_nov_frame(*, world_path: Path, cold_store: Path) -> CognitiveFrame:
    """The only live-world read; never construct a writer-side cold store."""
    if cold_store.is_symlink() or not cold_store.is_dir():
        raise RecallBlocked("cold_store_invalid")
    manifest = cold_store / "manifest.json"
    world_before, world = _read_bounded_json(world_path, MAX_WORLD_BYTES, "pilot_world")
    manifest_before, metadata = _read_bounded_json(manifest, MAX_MANIFEST_BYTES, "pilot_manifest")
    if (type(metadata.get("version")) is not int or metadata["version"] != 1
            or not isinstance(metadata.get("entity_region"), dict)):
        raise RecallBlocked("manifest_schema")
    region_id = metadata["entity_region"].get("nov")
    if not isinstance(region_id, str) or not 1 <= len(region_id) <= 160:
        raise RecallBlocked("nov_region_missing")
    if not all(c.isascii() and (c.isalnum() or c in "._:-") for c in region_id):
        raise RecallBlocked("nov_region_invalid")
    region_path = cold_store / "regions" / (
        sha256(region_id.encode("utf-8")).hexdigest() + ".json"
    )
    region_before, rows = _bounded_region(region_path)
    matches = [item for item in rows if item.get("id") == "nov"]
    if (len(matches) != 1 or matches[0].get("region_id") != region_id
            or not isinstance(world.get("world_id"), str)
            or not world["world_id"]):
        raise RecallBlocked("nov_entity_or_world_invalid")
    tick = world.get("current_tick", world.get("sequence"))
    if type(tick) is not int or tick < 0:
        raise RecallBlocked("world_tick_invalid")
    frame = build_nov_cognitive_frame(world=world, observer=matches[0], targets={})
    # Re-read all three atomic sources; never merge different generations.
    if (world_before != _read_bounded_json(world_path, MAX_WORLD_BYTES, "pilot_world")[0]
            or manifest_before != _read_bounded_json(
                manifest, MAX_MANIFEST_BYTES, "pilot_manifest"
            )[0]
            or region_before != _bounded_region(region_path)[0]):
        raise RecallBlocked("live_frame_generation_moved")
    return frame


class OwnerLiveFramePilot:
    """Bounded trial: 1 context/frame per cycle, no world writes or network.

    A running owner-side worker may be busy loading; peek is always
    nonblocking. No raw frame, IDs, addresses or outcomes are reported.
    """
    def __init__(self, *, frame_reader: Callable[[], CognitiveFrame],
                 preparer: OwnerAsyncDualLanePreparation,
                 cycles: int = 20, interval: float = 1.0,
                 _clock: Callable[[], float] = time.monotonic,
                 _sleep: Callable[[float], None] = time.sleep):
        if type(cycles) is not int or not 1 <= cycles <= MAX_CYCLES:
            raise RecallBlocked("pilot_cycle_budget")
        if type(interval) not in (int, float) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
            raise RecallBlocked("pilot_interval_budget")
        self.frame_reader = frame_reader
        self.preparer = preparer
        self.cycles = cycles
        self.interval = interval
        self._clock = _clock
        self._sleep = _sleep

    def run(self) -> dict[str, Any]:
        tally: Counter[str] = Counter()
        region_or_weather_changes = 0
        seen_ticks: set[int] = set()
        last_state: tuple[str, ...] | None = None
        primary_max = supplementary_max = 0
        started = self._clock()
        self.preparer.start()
        try:
            for _ in range(self.cycles):
                try:
                    frame = self.frame_reader()
                    state = tuple(a for a in frame.state_addresses
                                  if a.startswith(("live:region:", "live:weather:",
                                                   "live:period:")))
                    if last_state is not None and state != last_state:
                        region_or_weather_changes += 1
                    last_state = state
                    seen_ticks.add(frame.tick_id)
                    self.preparer.submit(frame)
                    # Bounded processing opportunity; never wait for the
                    # worker or enter the authoritative simulation's tick.
                    self._sleep(self.interval)
                    read = self.preparer.peek(frame)
                    status = read.status if read.status in ALLOWED_STATUS else "unavailable"
                    tally[status] += 1
                    if status == "ready":
                        primary_max = max(primary_max, read.public["primary_count"])
                        supplementary_max = max(
                            supplementary_max, read.public["supplementary_count"]
                        )
                except (OSError, ValueError, KeyError, TypeError):
                    tally["frame_unstable"] += 1
                    self._sleep(self.interval)
        finally:
            self.preparer.close()
        return {
            "schema": SCHEMA, "status": "completed",
            "cycles": self.cycles,
            "duration_seconds": round(max(0.0, self._clock() - started), 3),
            "distinct_live_frame_ticks": len(seen_ticks),
            "region_or_environment_transitions": region_or_weather_changes,
            "ready_reads": tally.get("ready", 0),
            "abstained_reads": self.cycles - tally.get("ready", 0),
            "statuses": dict(sorted(tally.items())),
            "max_primary_count": primary_max,
            "max_supplementary_count": supplementary_max,
            "bounded_trial_only": True,
            "actual_live_frame_read": True,
            "historical_memory_only": True,
            "main_runtime_wired": False,
            "selection_authority": False,
            "world_mutated": False,
            "central_sync": False,
            "bdr_used": False,
        }


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--cold-store", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    try:
        cache = VersionedNovRecallCache(
            private_root=args.private_root, source=args.source,
            checkpoint_path=args.checkpoint, world_path=args.world,
        )
        worker = OwnerAsyncDualLanePreparation(cache)
        trial = OwnerLiveFramePilot(
            frame_reader=lambda: read_current_nov_frame(
                world_path=args.world, cold_store=args.cold_store,
            ),
            preparer=worker, cycles=args.cycles, interval=args.interval,
        )
        output = trial.run()
    except (RecallBlocked, ValueError, OSError) as exc:
        raise SystemExit("MVP018L_PILOT_BLOCKED " + type(exc).__name__) from exc
    print("MVP018L_PILOT_OK " +
          json.dumps(output, sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
