"""Ingest chronological native navigation evidence; no authoritative world mutation."""
from __future__ import annotations
from hashlib import blake2b, sha256
from collections import Counter
import gzip
import os
import tempfile
import json
import math
from pathlib import Path
import re
from nov_spatial_memory_sync import _canonical, _post_local, _validate_ack, _observation_id
from nov_navigation_memory_sync import write_checkpoint, cell

SOURCE = Path("/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-navigation-episodes-008ch.json")
CHECKPOINT = Path("/var/lib/live-infinita/memoria-local/navigation-episodes.checkpoint.json")
SCHEMA = "live-infinita-nov-navigation-episodes/v1"
CP_SCHEMA = "live-infinita-nov-navigation-episodes-checkpoint/v2"
MAX_BYTES = 2_000_000
OUTCOMES = {"blocked", "step_reached", "goal_reached", "interrupted", "no_passage_sensed"}

def fail():
    raise ValueError("navigation_episode_invalid")

def number(value, bound=10_000_000_000):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > bound:
        fail()
    return value

def point(value):
    if not isinstance(value, list) or len(value) != 2:
        fail()
    return [number(v, 2048) for v in value]

def context(value):
    if not isinstance(value, dict):
        fail()
    world_id = value.get("world_id")
    if not isinstance(world_id, str) or not 1 <= len(world_id) <= 160:
        fail()
    if type(value.get("world_sequence")) is not int or value["world_sequence"] < 0:
        fail()
    if value.get("observer_entity_id") != "nov":
        fail()
    p = value.get("runtime_position")
    if not isinstance(p, dict):
        fail()
    number(p.get("x"), 10_000_000)
    number(p.get("y"), 10_000_000)
    return world_id

def validate_episode(row):
    if not isinstance(row, dict):
        fail()
    session = row.get("session_id")
    seq = row.get("sequence")
    if not isinstance(session, str) or not re.fullmatch("[0-9a-f]{32}", session):
        fail()
    if type(seq) is not int or seq < 1 or row.get("episode_id") != f"{session}:{seq}":
        fail()
    if row.get("coordinate_space") != "godot-renderer-xz-metres" or row.get("world_write_authority") is not False or row.get("chronological_episode") is not True:
        fail()
    actions = row.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 128:
        fail()
    last_time = -1
    for action in actions:
        if not isinstance(action, dict) or action.get("outcome") not in OUTCOMES:
            fail()
        if action.get("physical_attempt") is not (action["outcome"] != "no_passage_sensed"):
            fail()
        if type(action.get("collisions")) is not int or not 0 <= action["collisions"] <= 1:
            fail()
        if not isinstance(action.get("surface"), str) or len(action["surface"]) > 100:
            fail()
        start_world = context(action.get("context_start"))
        if context(action.get("context_end")) != start_world:
            fail()
        if action["context_end"]["world_sequence"] < action["context_start"]["world_sequence"]:
            fail()
        for name in ("start", "end", "goal", "selected"):
            point(action.get(name))
        for name in ("started_at_unix", "ended_at_unix", "started_at_ms", "duration_ms", "remaining_goal_m"):
            if number(action.get(name)) < 0:
                fail()
        # Sequence uses monotonic renderer milliseconds; wall clock may adjust.
        if action["started_at_ms"] < last_time:
            fail()
        last_time = action["started_at_ms"] + action["duration_ms"]
        if type(action.get("decision_serial")) is not int or action["decision_serial"] < 1:
            fail()
        if action.get("goal_kind") != "projected_runtime_observer_position":
            fail()
        source = action.get("decision_source")
        if source not in {"perception", "perception-no-passage", "local-experience", "memoria.ia", "perception-memory-agreement"}:
            fail()
        identity = action.get("memory_observation_id")
        if source == "memoria.ia":
            if not isinstance(identity, str) or not re.fullmatch("structural-event:[0-9a-f]{40}", identity):
                fail()
        elif identity != "":
            fail()
        perception = action.get("perception")
        if not isinstance(perception, dict) or perception.get("lookahead_m") != 3.0:
            fail()
        candidates = perception.get("candidates")
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 11:
            fail()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                fail()
            point(candidate.get("point"))
            if type(candidate.get("allowed")) is not bool or type(candidate.get("clear_ahead")) is not bool:
                fail()
            if not isinstance(candidate.get("reason"), str) or len(candidate["reason"]) > 100:
                fail()
        if "without_memoria" in perception:
            point(perception["without_memoria"])
        if not isinstance(action.get("reason"), str) or len(action["reason"]) > 100:
            fail()
    return row

def read_source(path):
    if path.is_symlink():
        fail()
    with path.open("rb") as f:
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        fail()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        fail()
    rows = data.get("episodes")
    if not isinstance(rows, list) or len(rows) > 16:
        fail()
    if type(data.get("dropped_episodes")) is not int or data["dropped_episodes"] < 0:
        fail()
    seen = set()
    for row in rows:
        validate_episode(row)
        if row["episode_id"] in seen:
            fail()
        seen.add(row["episode_id"])
    return data

def payload(row):
    actions = row["actions"]
    world_ids = list(dict.fromkeys(a["context_start"]["world_id"] for a in actions))
    # Episodes may span a world switch. Keep each action's original world identity.
    # Keep a bounded structural path; the archive retains every candidate and action.
    sampled = actions[::max(1, math.ceil(len(actions) / 15))]
    trail = [cell(actions[0]["start"])] + [cell(a["end"]) for a in sampled]
    if sampled[-1] is not actions[-1]:
        trail.append(cell(actions[-1]["end"]))
    archive = {"relative_path": "navigation-episodes/" + row["episode_id"].replace(":", "-") + ".json.gz",
               "sha256": sha256(_canonical(row)).hexdigest(), "encoding": "gzip-json-v1", "action_count": len(actions)}
    event = {
        "version": 1, "source_id": "live.infinita:nov:navigation-episode:" + row["session_id"],
        "sequence": row["sequence"], "byte_offset": 0, "byte_length": len(_canonical(row)),
        "trail": trail, "relation_ids": [int.from_bytes(blake2b(a["outcome"].encode(), digest_size=8).digest(), "big") for a in [next(a for a in actions if a["outcome"] == kind) for kind in sorted({a["outcome"] for a in actions})]],
        "signature": blake2b(_canonical(row), digest_size=8).hexdigest(), "resolution": 1,
    }
    return {"event": event, "provenance": {
        "hierarchy_id": "live:navigation:nov:episodes", "source_kind": "native_renderer_navigation_episode",
        "source_ledger": SOURCE.name, "entity_id": "nov", "world_ids": world_ids,
        "world_id_role": "recorded_world_feed_context", "authority": "observed-renderer-physical-results",
        "world_write_authority": False, "selection_authority": False, "chronological_episode": True,
        "coordinate_space": "godot-renderer-xz-metres", "episode_id": row["episode_id"],
        "episode_archive": archive, "outcomes": dict(Counter(a["outcome"] for a in actions)),
        "decision_sources": dict(Counter(a["decision_source"] for a in actions)),
        "memory_observation_ids": list(dict.fromkeys(a["memory_observation_id"] for a in actions if a["memory_observation_id"]))[:16],
        "structural_path_sampling": "at_most_17_cells_full_path_in_archive",
    }}

def archive_episode(row, root):
    info = payload(row)["provenance"]["episode_archive"]
    directory = root / "navigation-episodes"
    if directory.is_symlink():
        fail()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / info["relative_path"]
    if path.is_symlink():
        fail()
    raw = _canonical(row)
    if path.exists():
        if path.stat().st_size > MAX_BYTES:
            fail()
        with gzip.open(path, "rb") as f:
            existing = f.read(MAX_BYTES + 1)
        if existing != raw:
            raise ValueError("episode_archive_identity_changed")
        return info
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(gzip.compress(raw, mtime=0))
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return info

def sync_once(source=SOURCE, checkpoint=CHECKPOINT, send=_post_local, limit=2):
    if type(limit) is not int or not 1 <= limit <= 2:
        fail()
    if not source.exists():
        return {"status": "awaiting_native_episode", "acked": 0}
    data = read_source(source)
    state = {"schema": CP_SCHEMA, "seen": {}, "confirmed": 0}
    if checkpoint.is_symlink():
        fail()
    if checkpoint.exists():
        if checkpoint.stat().st_size > MAX_BYTES:
            fail()
        state = json.loads(checkpoint.read_text())
        if isinstance(state, dict) and state.get("schema") == "live-infinita-nov-navigation-episodes-checkpoint/v1":
            state = {"schema": CP_SCHEMA, "seen": {}, "confirmed": 0, "legacy_full_episode_confirmed": state.get("confirmed", 0)}
        if not isinstance(state, dict) or state.get("schema") != CP_SCHEMA or not isinstance(state.get("seen"), dict):
            fail()
        if len(state["seen"]) > 1024 or type(state.get("confirmed")) is not int or state["confirmed"] < 0:
            fail()
        for key, value in state["seen"].items():
            if not re.fullmatch("[0-9a-f]{32}:[1-9][0-9]*", key) or not re.fullmatch("structural-event:[0-9a-f]{40}", str(value)):
                fail()
    acked = 0
    for row in data["episodes"]:
        observation = payload(row)
        expected = _observation_id(observation["event"])
        existing = state["seen"].get(row["episode_id"])
        if existing:
            if existing != expected:
                raise ValueError("episode_identity_changed")
            continue
        # Preserve full evidence durably before acknowledging its compact memory address.
        archive_episode(row, checkpoint.parent)
        receipt = send(observation)
        _validate_ack(receipt, observation)
        if receipt["stored"] == receipt["duplicate"]:
            fail()
        state["seen"][row["episode_id"]] = expected
        while len(state["seen"]) > 1024:
            del state["seen"][next(iter(state["seen"]))]
        state["confirmed"] += 1
        state["last_observation_id"] = expected
        state["source_retention_dropped"] = data["dropped_episodes"]
        write_checkpoint(checkpoint, state)
        acked += 1
        if acked >= limit:
            break
    return {"status": "ok", "acked": acked, "confirmed": state["confirmed"],
            "source_retention_dropped": data["dropped_episodes"], "world_mutated": False}
