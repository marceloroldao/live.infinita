#!/usr/bin/env python3
"""One-shot, offline local Memoria.ia RC2 worker for Nov.

Never imports the LLM, opens a socket, invokes the central server or modifies
Nov's original episode ledger / single-writer world.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from packages.observability.local_memoria import (
    PINNED_MEMORIA_COMMIT, LocalMemoriaError, status, sync_once,
)

DEFAULT_WORLD_ROOT = Path("/var/lib/live-infinita/autonomous-world")
DEFAULT_LOCAL_DIR = Path("/var/lib/live-infinita/memoria-local")
DEFAULT_PIN_FILE = Path("/opt/live-infinita-memoria-rc2/commit.txt")


def _verify_source_pin(pin_file: Path) -> None:
    # The Python import path must be supplied by the invoking service;
    # the source pin is a separate immutable record made by the deploy.
    actual = pin_file.read_text(encoding="ascii").strip()
    if actual != PINNED_MEMORIA_COMMIT:
        raise LocalMemoriaError("local_memoria_source_pin_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description="Nov -> local Memoria.ia RC2, offline")
    parser.add_argument("--world-root", type=Path, default=DEFAULT_WORLD_ROOT)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    parser.add_argument("--pin-file", type=Path, default=DEFAULT_PIN_FILE)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        print(json.dumps(status(args.local_dir), sort_keys=True))
        return 0
    if not 1 <= args.limit <= 16:
        parser.error("--limit must be between 1 and 16")
    try:
        _verify_source_pin(args.pin_file)
        result = sync_once(
            args.world_root / "npc-episodes.jsonl",
            args.world_root / "world.json",
            args.local_dir,
            limit=args.limit,
        )
    except (LocalMemoriaError, FileNotFoundError, PermissionError, ValueError) as exc:
        print(json.dumps({
            "status": "blocked",
            "reason": str(exc),
            "central_transport_enabled": False,
            "world_mutated": False,
        }, ensure_ascii=False))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
