"""Publish current native counters without calling or writing Memoria.ia."""
from pathlib import Path
import json
import os
import time
import tempfile
import math
from nov_navigation_memory_sync import WORLD, _world_id, _canonical
from nov_navigation_recall_export import PANEL, PUBLIC as RECALL, SCHEMA as RECALL_SCHEMA, read_learning_status
PUBLIC = Path("/var/www/live-infinita-godot/navigation-memory/status.json")

def publish_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("panel_public_symlink")
    fd, name = tempfile.mkstemp(prefix=path.name+".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            # Permissions belong to the new inode before it becomes public.
            os.fchmod(fh.fileno(), 0o644)
            fh.write(_canonical(value)+b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def valid_quality(value):
    if not isinstance(value,dict):
        return False
    fields = [value.get(k) for k in ("samples","remaining_cost_m","reference_cost_m")]
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in fields):
        return False
    return fields[0]>=1 and fields[0]==int(fields[0]) and fields[2]<=fields[1]

def recall_metrics(path, world_id, now):
    unavailable = {"available":False}
    try:
        if path.is_symlink() or not path.exists() or path.stat().st_size > 2_000_000:
            return unavailable
        data = json.loads(path.read_text())
        if not isinstance(data,dict) or data.get("schema") != RECALL_SCHEMA or data.get("world_id") != world_id or data.get("source") != "memoria.ia-local-structural-api":
            return unavailable
        stamp = data.get("generated_at_unix")
        if isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not 0 <= now-stamp <= 180:
            return unavailable
        rows = data.get("entries")
        if not isinstance(rows,list) or len(rows)>4096:
            return unavailable
        successful = [x for x in rows if isinstance(x,dict) and x.get("kind")=="successful_route_step" and isinstance(x.get("observation_id"),str) and x["observation_id"].startswith("structural-event:") and len(x["observation_id"])==57]
        return {"available":True,"routes":len(successful),
                "with_cost":sum(valid_quality(x.get("route_quality")) for x in successful),
                "generated_at_unix":stamp,"source":"memoria.ia-local-structural-api"}
    except (OSError,ValueError,TypeError):
        return unavailable

def export_once(world=WORLD, source=PANEL, public=PUBLIC, now=time.time, recall=RECALL):
    world_id = _world_id(world)
    stamp = now()
    status = read_learning_status(source, world_id, stamp)
    result = {"schema":"live-infinita-nov-panel/v1", "source":"native_renderer_journey",
              "world_id":world_id, "generated_at_unix":stamp, "learning_status":status or {},
              "memoria_recall":recall_metrics(recall,world_id,stamp)}
    publish_atomic(public, result)
    return {"available":status is not None, "world_id":world_id}

if __name__ == "__main__":
    print("NOV_PANEL_EXPORT_OK " + json.dumps(export_once(), sort_keys=True))
