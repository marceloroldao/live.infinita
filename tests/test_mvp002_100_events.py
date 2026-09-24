#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ACTIONS = [
    "move_tree",
    "toggle_fire",
    "set_night",
    "set_day",
    "reset",
]


def request_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="MVP-002 deterministic 100-event VM battery")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Live Infinita runtime URL")
    parser.add_argument("--events", type=int, default=100, help="Number of events to generate")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    total = args.events
    if total <= 0:
        fail("--events must be > 0")

    try:
        before = request_json(f"{base}/api/replay/verify")
    except Exception as exc:
        fail(f"runtime unavailable at {base}: {exc}")

    start_events = int(before.get("events", -1))
    start_deltas = int(before.get("deltas", -1))
    start_sequence = int(before.get("sequence", -1))

    if not before.get("ok"):
        fail("baseline replay is already inconsistent before the battery")

    started = time.perf_counter()
    for i in range(total):
        action = ACTIONS[i % len(ACTIONS)]
        try:
            result = request_json(f"{base}/api/simulate", method="POST", payload={"action": action})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            fail(f"event {i + 1}/{total} action={action} returned HTTP {exc.code}: {body}")
        except Exception as exc:
            fail(f"event {i + 1}/{total} action={action} failed: {exc}")

        if not result.get("ok"):
            fail(f"event {i + 1}/{total} action={action} returned ok=false")

        world = result.get("world", {})
        expected_sequence = start_sequence + i + 1
        if int(world.get("sequence", -1)) != expected_sequence:
            fail(
                f"sequence mismatch after event {i + 1}: "
                f"expected {expected_sequence}, got {world.get('sequence')}"
            )
        if not world.get("state_hash"):
            fail(f"event {i + 1}/{total} produced no state_hash")

    elapsed = time.perf_counter() - started

    after = request_json(f"{base}/api/replay/verify")
    expected_events = start_events + total
    expected_deltas = start_deltas + total
    expected_sequence = start_sequence + total

    checks = {
        "Replay": bool(after.get("ok")),
        "Hash match": after.get("current_hash") == after.get("replay_hash"),
        "Event count": int(after.get("events", -1)) == expected_events,
        "Delta count": int(after.get("deltas", -1)) == expected_deltas,
        "Sequence": int(after.get("sequence", -1)) == expected_sequence,
    }

    print("MVP-002 DETERMINISM TEST")
    print(f"Events generated: {total}")
    print(f"Events total:     {after.get('events')} (expected {expected_events})")
    print(f"Deltas total:     {after.get('deltas')} (expected {expected_deltas})")
    print(f"Sequence:         {after.get('sequence')} (expected {expected_sequence})")
    print(f"Elapsed:          {elapsed:.3f}s")
    print(f"Rate:             {total / elapsed:.2f} events/s" if elapsed > 0 else "Rate:             n/a")
    print(f"Current hash:     {after.get('current_hash')}")
    print(f"Replay hash:      {after.get('replay_hash')}")
    for name, ok in checks.items():
        print(f"{name:<17} {'PASS' if ok else 'FAIL'}")

    passed = all(checks.values())
    print(f"Result:           {'VALIDATED' if passed else 'FAILED'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
