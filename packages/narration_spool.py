"""Append-only presentation cue transport, separate from authoritative World State."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

MAX_CUE_BYTES = 4096
READ_WINDOW_BYTES = 262144


def append_cue(path: Path, cue: dict[str, Any]) -> None:
    identity = str(cue.get("cue_id") or "").strip()
    text = str(cue.get("text") or "").strip()
    if not identity or not text:
        raise ValueError("narration cue requires cue_id and text")
    record = {"cue": cue, "created_at_unix": time.time()}
    data = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > MAX_CUE_BYTES:
        raise ValueError("narration cue too large")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
    try:
        if os.write(fd, data) != len(data):
            raise OSError("partial narration cue append")
        os.fsync(fd)
    finally:
        os.close(fd)


def resume_offset(path: Path, last_identity: str) -> int:
    """Resume after last queued cue without replaying old presentation speech."""
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            if not last_identity:
                return end
            start = max(0, end - READ_WINDOW_BYTES)
            f.seek(start)
            data = f.read()
    except OSError:
        return 0
    if start:
        cut = data.find(b"\n")
        if cut < 0:
            return end
        start += cut + 1
        data = data[cut + 1:]
    cursor = start
    result = None
    for raw in data.splitlines(keepends=True):
        cursor += len(raw)
        if not raw.endswith(b"\n"):
            break
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        cue = row.get("cue") if isinstance(row, dict) else None
        if isinstance(cue, dict) and cue.get("cue_id") == last_identity:
            result = cursor
    return result if result is not None else end


def read_cues(path: Path, offset: int) -> tuple[int, list[dict[str, Any]]]:
    """Read only complete bounded JSONL records; never load whole spool."""
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if offset > size:
                return size, []
            f.seek(offset)
            data = f.read(READ_WINDOW_BYTES)
    except OSError:
        return offset, []
    cut = data.rfind(b"\n")
    if cut < 0:
        return offset, []
    records: list[dict[str, Any]] = []
    for raw in data[:cut + 1].splitlines():
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        cue = row.get("cue") if isinstance(row, dict) else None
        if isinstance(cue, dict) and cue.get("cue_id") and cue.get("text"):
            records.append(cue)
    return offset + cut + 1, records
