"""Bounded, read-only operational telemetry for the Live Infinita Manager.

No replay verification, full JSONL scans, world writes, or secrets are exposed.
"""
from __future__ import annotations

import asyncio
from collections import deque
import json
import os
from pathlib import Path
import re
import time
from typing import Any
import urllib.request


class EventLoopLagMonitor:
    def __init__(self) -> None:
        self.samples_ms: deque[float] = deque(maxlen=60)
        self.last_sample_unix: float | None = None
        self._task: asyncio.Task[None] | None = None

    async def _probe(self) -> None:
        while True:
            target = time.monotonic() + 1.0
            await asyncio.sleep(1.0)
            self.samples_ms.append(round(max(0.0, time.monotonic() - target) * 1000.0, 2))
            self.last_sample_unix = time.time()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._probe(), name="manager-event-loop-lag")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "last_ms": self.samples_ms[-1] if self.samples_ms else None,
            "max_recent_ms": max(self.samples_ms) if self.samples_ms else None,
            "samples": len(self.samples_ms),
            "last_sample_unix": self.last_sample_unix,
        }


def _bounded_json(path: Path, limit: int = 65_536) -> dict[str, Any]:
    try:
        if path.stat().st_size > limit:
            return {}
        value = json.loads(path.read_bytes())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _last_jsonl_record(path: Path, limit: int = 32_768) -> dict[str, Any]:
    """Read the last complete record using a fixed byte bound."""
    try:
        with path.open("rb") as source:
            source.seek(0, os.SEEK_END)
            size = source.tell()
            if not size:
                return {}
            source.seek(max(0, size - limit))
            data = source.read(limit)
    except OSError:
        return {}
    if not data.endswith(b"\n"):
        cut = data.rfind(b"\n")
        data = data[:cut + 1] if cut >= 0 else b""
    lines = data.splitlines()
    if size > limit and lines:
        lines = lines[1:]
    for raw in reversed(lines):
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def _cpu_pressure() -> float | None:
    try:
        snapshot = Path("/proc/pressure/cpu").read_text(encoding="ascii")
    except OSError:
        return None
    for line in snapshot.splitlines():
        if line.startswith("some "):
            match = re.search(r"(?:^|\s)avg10=([0-9]+(?:\.[0-9]+)?)", line)
            if match:
                return float(match.group(1))
    return None


def _native_audio_metrics(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > 8192:
            return {}
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        return {}
    fields = {"voice_chunks", "chunks", "misses", "xruns", "render_avg_ms", "max_late_ms"}
    result: dict[str, Any] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key in fields:
            try:
                result[key] = float(value) if key.endswith("_ms") else int(value)
            except ValueError:
                continue
    return result


def _relay_health() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8092/health", timeout=0.8) as response:
            if response.status != 200:
                return {"available": False}
            raw = response.read(8192)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return {"available": False}
        return {
            "available": payload.get("ok") is True,
            "active_streams": payload.get("active_streams"),
            "max_clients": payload.get("max_clients"),
        }
    except (OSError, ValueError, UnicodeError):
        return {"available": False}


def runtime_snapshot(data_dir: Path, loop: dict[str, Any]) -> dict[str, Any]:
    """Only fixed-size sidecars and procfs are read; no authoritative world access."""
    now = time.time()
    try:
        load_1m = round(os.getloadavg()[0], 2)
    except OSError:
        load_1m = None
    renderer = _bounded_json(data_dir / "render-runtime-status.json")
    renderer_at = renderer.get("updated_at_unix")
    age = max(0.0, now - renderer_at) if isinstance(renderer_at, (int, float)) else None
    audio_dir = data_dir / "audio"
    status = _bounded_json(audio_dir / "status.json")
    last_event = _last_jsonl_record(audio_dir / "narration-events.jsonl")
    last_cue = _last_jsonl_record(audio_dir / "narration-cue-spool.jsonl")
    cue = last_cue.get("cue") if isinstance(last_cue.get("cue"), dict) else {}
    metrics = _native_audio_metrics(audio_dir / "native-metrics.txt")
    audio_at = status.get("updated_at_unix")
    audio_age = max(0.0, now - audio_at) if isinstance(audio_at, (int, float)) else None
    return {
        "generated_at_unix": now,
        "host": {
            "cpu_pressure_avg10_pct": _cpu_pressure(),
            "load_1m": load_1m,
            "logical_cpus": os.cpu_count(),
        },
        "api": loop,
        "renderer": {
            "available": bool(renderer) and age is not None and age < 30,
            "fps": renderer.get("godot_fps"),
            "capture_fps": renderer.get("capture_fps"),
            "governor_enabled": renderer.get("governor_enabled"),
            "updated_age_s": round(age, 1) if age is not None else None,
        },
        "audio": {
            "state": status.get("state"),
            "status_age_s": round(audio_age, 1) if audio_age is not None else None,
            "last_event_id": last_event.get("event_identity"),
            "last_tts_ok": last_event.get("ok") is True if last_event else None,
            "last_tts_provider": last_event.get("provider"),
            "last_pcm_bytes": last_event.get("queued_pcm_bytes"),
            "latest_cue_id": cue.get("cue_id"),
            "voice_chunks": metrics.get("voice_chunks"),
            "xruns": metrics.get("xruns"),
            "deadline_misses": metrics.get("misses"),
        },
        "audio_web": _relay_health(),
    }


async def async_runtime_snapshot(data_dir: Path, loop_monitor: EventLoopLagMonitor) -> dict[str, Any]:
    loop = loop_monitor.snapshot()
    return await asyncio.to_thread(runtime_snapshot, data_dir, loop)
