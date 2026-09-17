from __future__ import annotations

import os
from pathlib import Path

from autonomous_runtime import build_authoritative_autonomous_runtime
from cognitive_shadow import CognitiveShadowRecorder
from shadow_world_tick import ShadowWorldTickRunner
from tick_driver_main import run_driver


def _required_env(name: str) -> str:
    value = str(os.getenv(name, "")).strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _flag_enabled(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


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


def _runner_with_optional_shadow(runtime, data_dir: Path):
    enabled = _flag_enabled("LIVE_INFINITA_MEMORIA_V2_SHADOW")
    if not enabled:
        return runtime.world_tick
    recorder = CognitiveShadowRecorder(
        data_dir / "memoria-v2-shadow.jsonl",
        world_provider=runtime.engine.load_world,
        store=runtime.store,
        observer_id="nov",
        enabled=True,
    )
    return ShadowWorldTickRunner(runtime.world_tick, recorder)


def main() -> None:
    """Start autonomous simulation only when this dedicated process is invoked."""
    runtime = build_from_environment()
    data_dir = Path(_required_env("LIVE_INFINITA_DATA_DIR"))
    run_driver(_runner_with_optional_shadow(runtime, data_dir), data_dir)


if __name__ == "__main__":
    main()
