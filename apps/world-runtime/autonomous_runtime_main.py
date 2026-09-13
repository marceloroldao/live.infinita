from __future__ import annotations

import os
from pathlib import Path

from autonomous_runtime import build_authoritative_autonomous_runtime
from tick_driver_main import run_driver


def _required_env(name: str) -> str:
    value = str(os.getenv(name, "")).strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _npc_ids() -> list[str]:
    raw = _required_env("LIVE_INFINITA_NPC_IDS")
    values = sorted({value.strip() for value in raw.split(",") if value.strip()})
    if not values:
        raise RuntimeError("LIVE_INFINITA_NPC_IDS must contain at least one id")
    return values


def build_from_environment():
    data_dir = Path(_required_env("LIVE_INFINITA_DATA_DIR"))
    cold_store_dir = Path(_required_env("LIVE_INFINITA_COLD_STORE_DIR"))
    bootstrap_file = Path(_required_env("LIVE_INFINITA_COLD_BOOTSTRAP_FILE"))
    try:
        tick_ms = int(str(os.getenv("LIVE_INFINITA_TICK_DURATION_MS", "500")).strip())
    except ValueError as exc:
        raise RuntimeError("LIVE_INFINITA_TICK_DURATION_MS must be an integer") from exc
    if tick_ms <= 0:
        raise RuntimeError("LIVE_INFINITA_TICK_DURATION_MS must be positive")

    return build_authoritative_autonomous_runtime(
        bootstrap_file=bootstrap_file,
        data_dir=data_dir,
        cold_store_dir=cold_store_dir,
        npc_ids=_npc_ids(),
        tick_duration_ms=tick_ms,
    )


def main() -> None:
    """Start autonomous simulation only when this dedicated process is invoked."""
    runtime = build_from_environment()
    run_driver(runtime.world_tick, Path(_required_env("LIVE_INFINITA_DATA_DIR")))


if __name__ == "__main__":
    main()
