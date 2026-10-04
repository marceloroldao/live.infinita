"""Mirror native renderer navigation summaries into local Memoria.ia.
Summaries are not world deltas, chronological episodes, or decision authority.
The renderer's cfg remains read-only; each acknowledgement is checked before
recording a content-derived observation ID. Unchanged content is never reinforced.
"""
from __future__ import annotations
import argparse
from hashlib import blake2b, sha256
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Callable

from nov_spatial_memory_sync import _canonical, _post_local, _validate_ack, _observation_id, _world_id

SOURCE = Path("/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-navigation-008cd.cfg")
WORLD = Path("/var/lib/live-infinita/autonomous-world/world.json")
CHECKPOINT = Path("/var/lib/live-infinita/memoria-local/nov-navigation-ingest.checkpoint.json")
SCHEMA = "live-infinita-nov-navigation-checkpoint/v1"
LIMIT = 4096
MAX_BYTES = 2_000_000
POINT = r"-?\d+,-?\d+"
NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
FORMAT = re.compile(r"\s*\[experience\]\s+failures=\{(?P<failures>.*?)\}\s+routes=\{(?P<routes>.*?)\}\s*", re.S)
FAILURE_ROW = re.compile(r'("'+POINT+r">"+POINT+r'"):\s*(\d+)')
ROUTE_ROW = re.compile(r'("'+POINT+r"\|"+POINT+r'"):\s*Vector2\(('+NUMBER+r"),\s*("+NUMBER+r")\)")

class NavigationSyncError(RuntimeError):
    pass

def point(text: str) -> list[float]:
    values = [float(v) for v in text.split(",")]
    if len(values) != 2 or any(not math.isfinite(v) or abs(v) > 2048 for v in values):
        raise NavigationSyncError("point_invalid")
    return values

def cell(values: list[float]) -> int:
    a, b = [int(round(v)) for v in values]
    a, b = [v * 2 if v >= 0 else -v * 2 - 1 for v in (a,b)]
    return (a+b)*(a+b+1)//2+b

def read_snapshot(path: Path) -> tuple[list[dict], str]:
    if path.is_symlink():
        raise NavigationSyncError("source_symlink")
    with path.open("rb") as fh:
        raw = fh.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        raise NavigationSyncError("source_oversized")
    match = FORMAT.fullmatch(raw.decode("utf-8"))
    if match is None:
        raise NavigationSyncError("source_incomplete_or_invalid")
    items = []
    for section in ("failures","routes"):
        rows = match[section].strip()
        rows = [] if not rows else rows.splitlines()
        if len(rows) > LIMIT:
            raise NavigationSyncError("source_entry_limit")
        seen = set()
        for index, line in enumerate(rows):
            line = line.strip()
            if line.endswith(","):
                line = line[:-1]
            elif index < len(rows)-1:
                raise NavigationSyncError("source_separator")
            row = (FAILURE_ROW if section == "failures" else ROUTE_ROW).fullmatch(line)
            if row is None:
                raise NavigationSyncError("source_entry_invalid")
            key = json.loads(row[1])
            if key in seen:
                raise NavigationSyncError("duplicate_source_key")
            seen.add(key)
            if section == "failures":
                start, end = key.split(">")
                count = int(row[2])
                if not 1 <= count <= 100:
                    raise NavigationSyncError("failure_count_invalid")
                item = {"kind":"blocked_passage", "key":key, "from":point(start), "to":point(end), "observed_count":count}
            else:
                goal, start = key.split("|")
                end = [float(row[2]),float(row[3])]
                if any(not math.isfinite(v) or abs(v)>2048 for v in end):
                    raise NavigationSyncError("route_point_invalid")
                item = {"kind":"successful_route_step", "key":key, "from":point(start), "to":end, "goal":point(goal), "observed_count":1}
            items.append(item)
    return items, sha256(raw).hexdigest()

def payload(item: dict, world_id: str, snapshot_hash: str) -> dict:
    identity = blake2b(_canonical({"kind":item["kind"],"key":item["key"]}),digest_size=16).hexdigest()
    event = {
        "version":1,
        "source_id":f"live.infinita:{world_id}:nov:renderer-navigation-summary:{identity}",
        "sequence":item["observed_count"],
        "byte_offset":0,
        "byte_length":len(_canonical(item)),
        "trail":[cell(item["from"]),cell(item["to"])],
        "relation_ids":[int.from_bytes(blake2b(item["kind"].encode(),digest_size=8).digest(),"big")],
        "signature":blake2b(_canonical(item),digest_size=8).hexdigest(),
        "resolution":1,
    }
    return {
        "event":event,
        "provenance":{
            "hierarchy_id":f"live:navigation:{world_id}:nov:renderer",
            "source_kind":"native_renderer_navigation_summary",
            "source_ledger":"nov-navigation-008cd.cfg",
            "snapshot_sha256":snapshot_hash,
            "world_id":world_id,
            "world_id_role":"current_runtime_context_only",
            "observation_granularity":"aggregate_snapshot",
            "entity_id":"nov",
            "authority":"observed-renderer-navigation-summary",
            "coordinate_space":"godot-renderer-xz-metres",
            "world_write_authority":False,
            "selection_authority":False,
            "chronological_episode":False,
            "summary":item,
        },
    }

def read_checkpoint(path: Path, world_id: str) -> dict:
    if path.is_symlink():
        raise NavigationSyncError("checkpoint_symlink")
    if not path.exists():
        return {"schema":SCHEMA,"world_id":world_id,"seen":{},"confirmed":0}
    if path.stat().st_size > MAX_BYTES:
        raise NavigationSyncError("checkpoint_oversized")
    value = json.loads(path.read_text())
    if not isinstance(value,dict) or value.get("schema") != SCHEMA or value.get("world_id") != world_id:
        raise NavigationSyncError("checkpoint_identity")
    seen = value.get("seen")
    if not isinstance(seen,dict) or len(seen)>LIMIT*2 or any(
        not re.fullmatch(r"[0-9a-f]{32}",k) or not isinstance(v,str) or not re.fullmatch(r"structural-event:[0-9a-f]{40}",v)
        for k,v in seen.items()
    ) or type(value.get("confirmed")) is not int or value["confirmed"] < 0:
        raise NavigationSyncError("checkpoint_invalid")
    return value

def write_checkpoint(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():
        raise NavigationSyncError("checkpoint_symlink")
    fd, name = tempfile.mkstemp(prefix=path.name+".",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as fh:
            fh.write(_canonical(value)+b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name,path)
        directory = os.open(path.parent,os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def sync_once(source: Path = SOURCE, world: Path = WORLD, checkpoint: Path = CHECKPOINT,
              send: Callable = _post_local, limit: int = 2, preview: bool = False) -> dict:
    if type(limit) is not int or not 1<=limit<=2:
        raise NavigationSyncError("invalid_limit")
    world_id = _world_id(world)
    items, digest = read_snapshot(source)
    if preview:
        return {"status":"preview","blocked_passages":sum(i["kind"]=="blocked_passage" for i in items),
                "successful_steps":sum(i["kind"]=="successful_route_step" for i in items),
                "snapshot_sha256":digest,"world_mutated":False,"selection_authority":False}
    state = read_checkpoint(checkpoint,world_id)
    current_keys = {blake2b(_canonical({"kind":i["kind"],"key":i["key"]}),digest_size=16).hexdigest() for i in items}
    state["seen"] = {k:v for k,v in state["seen"].items() if k in current_keys}
    acked = stored = 0
    blocked = [i for i in items if i["kind"] == "blocked_passage"]
    successful = [i for i in items if i["kind"] == "successful_route_step"]
    ordered = []
    for index in range(max(len(blocked),len(successful))):
        if index < len(blocked):
            ordered.append(blocked[index])
        if index < len(successful):
            ordered.append(successful[index])
    for item in ordered:
        observation = payload(item,world_id,digest)
        key = observation["event"]["source_id"].rsplit(":",1)[-1]
        expected = _observation_id(observation["event"])
        if state["seen"].get(key) == expected:
            continue
        receipt = send(observation)
        _validate_ack(receipt,observation)
        if receipt["stored"] == receipt["duplicate"]:
            raise NavigationSyncError("durable_ack_status_invalid")
        state["seen"][key] = expected
        state["confirmed"] += 1
        state["last_observation_id"] = expected
        state["snapshot_sha256"] = digest
        write_checkpoint(checkpoint,state)
        acked += 1
        stored += int(receipt["stored"])
        if acked >= limit:
            break
    return {"status":"ok","acked":acked,"stored":stored,"confirmed":state["confirmed"],
            "world_mutated":False,"selection_authority":False,"source":"native-renderer-summary"}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview",action="store_true")
    args = parser.parse_args()
    try:
        result = sync_once(preview=args.preview)
    except (OSError,ValueError,RuntimeError) as exc:
        raise SystemExit(f"NAVIGATION_MEMORY_SYNC_BLOCKED {type(exc).__name__}: {exc}") from exc
    print("NAVIGATION_MEMORY_SYNC_OK "+json.dumps(result,sort_keys=True))
if __name__ == "__main__":
    main()
