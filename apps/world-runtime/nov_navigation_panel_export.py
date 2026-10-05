"""Publish current native counters without calling or writing Memoria.ia."""
from pathlib import Path
import json
import os
import time
import tempfile
from nov_navigation_memory_sync import WORLD, _world_id, _canonical
from nov_navigation_recall_export import PANEL, read_learning_status
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

def export_once(world=WORLD, source=PANEL, public=PUBLIC, now=time.time):
    world_id = _world_id(world)
    stamp = now()
    status = read_learning_status(source, world_id, stamp)
    result = {"schema":"live-infinita-nov-panel/v1", "source":"native_renderer_journey",
              "world_id":world_id, "generated_at_unix":stamp, "learning_status":status or {}}
    publish_atomic(public, result)
    return {"available":status is not None, "world_id":world_id}

if __name__ == "__main__":
    print("NOV_PANEL_EXPORT_OK " + json.dumps(export_once(), sort_keys=True))
