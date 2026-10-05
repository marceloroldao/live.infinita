extends RefCounted
# Temporary route experiences. Reads never count as reuse.
signal promotion_ready

const LIMIT := 512
const TTL_MS := 600000
const REUSES_REQUIRED := 3
var enabled := false
var world_id := ""
var entries: Dictionary = {}
var promoted: Dictionary = {}
var session := Crypto.new().generate_random_bytes(16).hex_encode()
var storage := "user://nov-navigation-promotions-008ci.json"
var causal_reuses := 0

func _init(path: String = "user://nov-navigation-promotions-008ci.json") -> void:
    storage = path

func set_context(value: Dictionary) -> void:
    var identity := str(value.get("world_id", ""))
    if identity != world_id:
        entries.clear()
        promoted.clear()
        world_id = identity
        if not storage.is_empty() and FileAccess.file_exists(storage):
            var file := FileAccess.open(storage, FileAccess.READ)
            if file != null and file.get_length() < 2000000:
                var saved = JSON.parse_string(file.get_as_text())
                if typeof(saved) == TYPE_DICTIONARY and saved.get("world_id", "") == identity and saved.get("schema", "") == "live-infinita-nov-navigation-promotions/v1":
                    var rows = saved.get("entries", [])
                    if typeof(rows) == TYPE_ARRAY and rows.size() <= LIMIT:
                        for row in rows:
                            if typeof(row) == TYPE_DICTIONARY and typeof(row.get("summary")) == TYPE_DICTIONARY:
                                promoted[str(row["summary"].get("key", ""))] = row
        if not identity.is_empty() and not OS.has_feature("web") and not OS.get_cmdline_user_args().has("--offline-tour"):
            save()
    enabled = not identity.is_empty() and str(value.get("observer_entity_id", "")) == "nov" and not OS.has_feature("web") and not OS.get_cmdline_user_args().has("--offline-tour")

func address(goal: Array, start: Array) -> String:
    return "%d,%d|%d,%d" % [roundi(float(goal[0])), roundi(float(goal[1])), roundi(float(start[0])), roundi(float(start[1]))]

func prune(now_ms: int) -> void:
    for key in entries.keys():
        if now_ms - int(entries[key]["last_ms"]) > TTL_MS:
            entries.erase(key)
    while entries.size() > LIMIT:
        entries.erase(entries.keys()[0])

func lookup(key: String, now_ms: int = -1) -> Dictionary:
    if not enabled:
        return {}
    if now_ms < 0:
        now_ms = Time.get_ticks_msec()
    prune(now_ms)
    return Dictionary(entries.get(key, {})).duplicate(true)

func invalidate_candidate(key: String) -> void:
    # A sensed contradiction invalidates the temporary recommendation, not
    # historical promotions and not a fabricated failed movement.
    entries.erase(key)

func observe_completed(action: Dictionary, now_ms: int = -1) -> void:
    if not enabled or action.get("context_start", {}).get("world_id", "") != world_id:
        return
    if now_ms < 0:
        now_ms = Time.get_ticks_msec()
    var key := address(action["goal"], action["start"])
    var outcome := str(action.get("outcome", ""))
    if outcome == "blocked":
        entries.erase(key)
        return
    if outcome != "step_reached" and outcome != "goal_reached":
        return
    var selected: Array = action["selected"]
    var resolved: Array = action["end"]
    if Vector2(float(selected[0]), float(selected[1])).distance_to(Vector2(float(resolved[0]), float(resolved[1]))) > 0.03:
        return
    prune(now_ms)
    var item: Dictionary = entries.get(key, {})
    var next := Vector2(float(selected[0]), float(selected[1]))
    if item.is_empty() or Vector2(float(item["to"][0]), float(item["to"][1])).distance_to(next) > 0.05:
        item = {"to": selected.duplicate(), "reuses": 0, "evidence": [], "last_serial": 0}
    var reuse := bool(action.get("working_memory_changed_choice", false)) and str(action.get("working_memory_key", "")) == key
    if reuse and int(action["decision_serial"]) > int(item.get("last_serial", 0)) and int(item["reuses"]) < REUSES_REQUIRED:
        var action_id := session + ":" + str(int(action["decision_serial"]))
        var proof: Array = item["evidence"]
        if not proof.has(action_id):
            proof.append(action_id)
            item["reuses"] = int(item["reuses"]) + 1
            causal_reuses += 1
            if proof.size() > REUSES_REQUIRED:
                proof.pop_front()
    item["last_serial"] = maxi(int(item.get("last_serial", 0)), int(action["decision_serial"]))
    item["last_ms"] = now_ms
    entries.erase(key) # Insertion order acts as a bounded least-recent-success cache.
    entries[key] = item
    prune(now_ms)
    var already_promoted := false
    if promoted.has(key):
        var previous: Array = promoted[key]["summary"]["to"]
        already_promoted = Vector2(float(previous[0]), float(previous[1])).distance_to(next) <= 0.05
    if int(item["reuses"]) >= REUSES_REQUIRED and not already_promoted:
        var parts := key.split("|")
        var goal := parts[0].split(",")
        var start := parts[1].split(",")
        var summary := {"kind": "successful_route_step", "key": key,
            "from": [float(start[0]), float(start[1])], "to": selected.duplicate(),
            "goal": [float(goal[0]), float(goal[1])], "observed_count": 1}
        promoted[key] = {"summary": summary, "successful_causal_reuses": REUSES_REQUIRED,
            "decision_ids": Array(item["evidence"]).slice(-REUSES_REQUIRED),
            "promoted_at_unix": Time.get_unix_time_from_system()}
        while promoted.size() > LIMIT:
            promoted.erase(promoted.keys()[0])
        save()
        promotion_ready.emit()
        print("NOV_WORKING_MEMORY_PROMOTED key=%s successful_reuses=%d" % [key, REUSES_REQUIRED])

func save() -> void:
    if storage.is_empty():
        return
    var data := {"schema": "live-infinita-nov-navigation-promotions/v1",
        "world_id": world_id, "source": "native_renderer_working_memory",
        "world_write_authority": false, "entries": promoted.values()}
    var file := FileAccess.open(storage + ".tmp", FileAccess.WRITE)
    if file == null:
        push_warning("NOV_WORKING_MEMORY_SAVE_FAILED")
        return
    file.store_string(JSON.stringify(data))
    file.flush()
    file.close()
    if DirAccess.rename_absolute(storage + ".tmp", storage) != OK:
        push_warning("NOV_WORKING_MEMORY_SAVE_FAILED rename")
