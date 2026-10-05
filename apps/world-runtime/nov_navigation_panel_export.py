"""Publish current native counters without calling or writing Memoria.ia."""
from pathlib import Path
import json
import os
import time
from nov_navigation_memory_sync import WORLD, _world_id, write_checkpoint
from nov_navigation_recall_export import PANEL, read_learning_status
PUBLIC = Path("/var/www/live-infinita-godot/navigation-memory/status.json")

def export_once(world=WORLD, source=PANEL, public=PUBLIC, now=time.time):
    world_id = _world_id(world)
    stamp = now()
    status = read_learning_status(source, world_id, stamp)
    result = {"schema":"live-infinita-nov-panel/v1", "source":"native_renderer_journey",
              "world_id":world_id, "generated_at_unix":stamp, "learning_status":status or {}}
    write_checkpoint(public, result)
    os.chmod(public, 0o644)
    return {"available":status is not None, "world_id":world_id}

if __name__ == "__main__":
    print("NOV_PANEL_EXPORT_OK " + json.dumps(export_once(), sort_keys=True))
