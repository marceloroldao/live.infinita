"""Explicit one-shot Nov observed-episode delivery.

Not part of the autonomous world, API, Godot, or system startup. Enabling an
environment variable does not start a loop or create a service.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

from packages.observability.nov_episode_delivery import DeviceSession, DeliveryError, deliver_next

MAX_RECORDS_PER_RUN = 16
REQUIRED = (
    "LIVE_INFINITA_NOV_SYNC_SERVER_URL",
    "LIVE_INFINITA_NOV_SYNC_SERVER_ID",
    "LIVE_INFINITA_NOV_SYNC_DEVICE_ID",
    "LIVE_INFINITA_NOV_SYNC_PRIVATE_KEY",
    "LIVE_INFINITA_NOV_SYNC_WORLD_DIR",
    "LIVE_INFINITA_NOV_SYNC_CHECKPOINT",
)


def configured_session(env: dict[str, str]) -> tuple[DeviceSession, Path, Path, Path]:
    if env.get("LIVE_INFINITA_NOV_SYNC_ENABLED") != "1":
        raise DeliveryError("observational transport disabled by default")
    values = {name: str(env.get(name) or "").strip() for name in REQUIRED}
    if not all(values.values()):
        raise DeliveryError("explicit central identity, world paths and private key are required")
    key_path = Path(values["LIVE_INFINITA_NOV_SYNC_PRIVATE_KEY"])
    if key_path.is_symlink() or not key_path.is_file():
        raise DeliveryError("device private key must be a regular file, not a symlink")
    key_stat = key_path.stat()
    if key_stat.st_uid != os.geteuid() or stat.S_IMODE(key_stat.st_mode) & 0o077:
        raise DeliveryError("device private key must be owned by runner and mode 0600")
    world_dir = Path(values["LIVE_INFINITA_NOV_SYNC_WORLD_DIR"])
    checkpoint = Path(values["LIVE_INFINITA_NOV_SYNC_CHECKPOINT"])
    if checkpoint.is_relative_to(world_dir):
        raise DeliveryError("sync checkpoint must stay outside authoritative world tree")
    device = DeviceSession(
        server_url=values["LIVE_INFINITA_NOV_SYNC_SERVER_URL"],
        server_id=values["LIVE_INFINITA_NOV_SYNC_SERVER_ID"],
        device_id=values["LIVE_INFINITA_NOV_SYNC_DEVICE_ID"],
        key_path=key_path,
    )
    return device, world_dir / "npc-episodes.jsonl", world_dir / "world.json", checkpoint


def run_once(env: dict[str, str], *, max_records: int = 1) -> dict[str, int | str]:
    if not 1 <= max_records <= MAX_RECORDS_PER_RUN:
        raise DeliveryError("invalid bounded record limit")
    device, episodes, world, checkpoint = configured_session(env)
    statuses: dict[str, int] = {}
    for _ in range(max_records):
        result = deliver_next(
            episode_file=episodes, world_file=world,
            checkpoint_file=checkpoint, device=device,
        )
        state = str(result["status"])
        statuses[state] = statuses.get(state, 0) + 1
        if state == "waiting_complete_record":
            break
    return {"mode": "one-shot-observational-sync", **statuses}


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot observed Nov episode sync")
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--max-records", type=int, default=1)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = run_once(dict(os.environ), max_records=args.max_records)
    except Exception as exc:
        # No credentials, envelope, comments, upstream body or URL in stdout.
        raise SystemExit("NOV_SYNC_NOT_ACKNOWLEDGED " + type(exc).__name__) from None
    print("NOV_SYNC_RESULT " + " ".join(f"{key}={value}" for key, value in sorted(result.items())))


if __name__ == "__main__":
    main()
