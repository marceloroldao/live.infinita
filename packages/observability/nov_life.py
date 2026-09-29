"""Read-only, bounded projection of Nov's *actual* NPC episode ledger.

Never promotes narration, LLM output or shadow forecasts to experienced facts.
The authoritative autonomous-world process remains the sole writer.
"""
from __future__ import annotations

import math
from pathlib import Path
import time
from typing import Any

from packages.observability.runtime_metrics import recent_jsonl

MAX_WINDOW_BYTES = 262_144
MAX_WINDOW_RECORDS = 256
MAX_DISPLAY_EPISODES = 8


def _short_string(value: Any, *, limit: int = 96) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit:
        return None
    if not all(c.isalnum() or c in "._:-" for c in cleaned):
        return None
    return cleaned


def _bounded_number(value: Any, *, low: float = 0.0, high: float = 1.0) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return round(parsed, 3) if math.isfinite(parsed) and low <= parsed <= high else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return parsed if 0 <= parsed <= 10**12 else None


def project_confirmed_episode(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("episode_schema") != "npc_episode_v1" or row.get("npc_id") != "nov":
        return None
    episode_id = _short_string(row.get("episode_id"), limit=160)
    tick = _nonnegative_int(row.get("logical_tick"))
    if episode_id is None or tick is None:
        return None
    context = row.get("context") if isinstance(row.get("context"), dict) else {}
    outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
    need = _short_string(row.get("need"))
    return {
        "episode_id": episode_id,
        "logical_tick": tick,
        "need": need,
        "target_entity_id": _short_string(row.get("target_entity_id")),
        "strategy_id": _short_string(row.get("strategy_id"), limit=128),
        "context": {
            "region_id": _short_string(context.get("region_id")),
            "period": _short_string(context.get("period")),
            "weather": _short_string(context.get("weather")),
            "danger_level": _bounded_number(context.get("danger_level")),
        },
        "outcome": {
            "satisfaction": _bounded_number(outcome.get("satisfaction")),
            "observed_risk": _bounded_number(outcome.get("observed_risk")),
            "elapsed_ticks": _nonnegative_int(outcome.get("elapsed_ticks")),
            "preemptions": _nonnegative_int(outcome.get("preemptions")),
            "replans": _nonnegative_int(outcome.get("replans")),
        },
        "provenance": "npc_episode_v1",
    }


def nov_life_snapshot(
    episode_file: Path,
    *,
    max_bytes: int = MAX_WINDOW_BYTES,
    window_records: int = MAX_WINDOW_RECORDS,
    limit: int = MAX_DISPLAY_EPISODES,
) -> dict[str, Any]:
    """Constant upper-bound I/O and no ledger writes or whole-history scans."""
    max_bytes = max(1, min(int(max_bytes), MAX_WINDOW_BYTES))
    window_records = max(1, min(int(window_records), MAX_WINDOW_RECORDS))
    limit = max(0, min(int(limit), MAX_DISPLAY_EPISODES))
    path = Path(episode_file)
    available = path.is_file()
    rows = recent_jsonl(path, max_bytes=max_bytes, limit=window_records)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reversed(rows):
        episode = project_confirmed_episode(row)
        if episode is None or episode["episode_id"] in seen:
            continue
        seen.add(episode["episode_id"])
        if len(selected) < limit:
            selected.append(episode)
    return {
        "ok": True,
        "mode": "read-only-local-episodes",
        "observer_id": "nov",
        "ledger_available": available,
        "source_scope": "recent_window",
        "max_window_bytes": max_bytes,
        "window_records_examined": len(rows),
        "episodes": selected,
        "latest_episode_tick": selected[0]["logical_tick"] if selected else None,
        "world_mutated": False,
        "selection_authority": False,
        "central_memoria_sync": False,
        "generated_at_unix": time.time(),
    }
