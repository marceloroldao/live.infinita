extends RefCounted
# Native presentation evidence. This recorder never writes authoritative World State.
signal action_completed(action: Dictionary)

const SCHEMA := "live-infinita-nov-navigation-episodes/v1"
const MAX_BYTES := 1900000
var storage := "user://nov-navigation-episodes-008ch.json"
var enabled := false
var context: Dictionary = {}
var episodes: Array = []
var actions: Array = []
var active: Dictionary = {}
var session := ""
var sequence := 0
var last_flush_ms := 0
var last_no_passage_ms := -10000
var dropped := 0

func _init(path: String = "user://nov-navigation-episodes-008ch.json") -> void:
    storage = path
    session = Crypto.new().generate_random_bytes(16).hex_encode()
    if not storage.is_empty() and FileAccess.file_exists(storage):
        var value = JSON.parse_string(FileAccess.get_file_as_string(storage))
        if typeof(value) == TYPE_DICTIONARY and value.get("schema") == SCHEMA:
            episodes = value.get("episodes", [])
            dropped = int(value.get("dropped_episodes", 0))
    enabled = false # Only the live authoritative feed branch enables recording.

func set_context(value: Dictionary) -> void:
    if value.get("world_id", "") != context.get("world_id", ""):
        # An unfinished action cannot cross world identities.
        active = {}
    context = value.duplicate(true)

func point(value: Vector3) -> Array:
    return [value.x, value.z]

func observe(serial: int, current: Vector3, goal: Vector3, selected: Vector2,
        evidence: Dictionary, policy: Dictionary, now_ms: int = -1) -> void:
    if now_ms < 0:
        now_ms = Time.get_ticks_msec()
    if not enabled or context.get("world_id", "").is_empty():
        return
    if not active.is_empty() and int(active["decision_serial"]) != serial:
        _finish("interrupted", current, now_ms, "new_decision")
    var no_passage := str(policy.get("decision_source", "")) == "perception-no-passage"
    if no_passage and now_ms - last_no_passage_ms < 10000:
        tick(now_ms)
        return
    if active.is_empty():
        active = {
            "route_goal_id": str(policy.get("route_goal_id", "")),
            "decision_serial": serial, "started_at_unix": Time.get_unix_time_from_system(),
            "started_at_ms": now_ms, "start": point(current), "goal": point(goal),
            "goal_kind": "projected_runtime_observer_position",
            "selected": [selected.x, selected.y], "context_start": context.duplicate(true),
            "perception": evidence.duplicate(true),
            "decision_source": policy.get("decision_source", ""),
            "memory_observation_id": policy.get("memory_observation_id", ""),
            "working_memory_session": policy.get("working_memory_session", ""),
            "working_memory_key": policy.get("working_memory_key", ""),
            "working_memory_changed_choice": bool(policy.get("working_memory_changed_choice", false)),
        }
    active["collisions"] = int(policy.get("collisions", 0))
    active["surface"] = str(policy.get("surface", "terrain"))
    var resolved: Vector3 = policy.get("position", current)
    if no_passage:
        last_no_passage_ms = now_ms
        _finish("no_passage_sensed", resolved, now_ms, str(policy.get("reason", "")))
    elif not bool(policy.get("allowed", false)) or int(policy.get("collisions", 0)) > 0:
        _finish("blocked", resolved, now_ms, str(policy.get("reason", "blocked")))
    elif bool(policy.get("reached", false)):
        _finish("goal_reached", resolved, now_ms, "")
    elif Vector2(resolved.x, resolved.z).distance_to(selected) < 0.03:
        _finish("step_reached", resolved, now_ms, "")
    tick(now_ms)

func _finish(outcome: String, resolved: Vector3, now_ms: int, reason: String) -> void:
    var remaining := Vector2(resolved.x, resolved.z).distance_to(Vector2(float(active["goal"][0]), float(active["goal"][1])))
    if outcome == "goal_reached" and remaining >= 0.1:
        outcome = "interrupted"
        reason = "runtime_goal_changed"
    active["physical_attempt"] = outcome != "no_passage_sensed"
    active["outcome"] = outcome
    active["reason"] = reason
    active["end"] = point(resolved)
    active["ended_at_unix"] = Time.get_unix_time_from_system()
    active["duration_ms"] = maxi(0, now_ms - int(active["started_at_ms"]))
    active["context_end"] = context.duplicate(true)
    active["remaining_goal_m"] = remaining
    actions.append(active)
    action_completed.emit(active.duplicate(true))
    active = {}

func tick(now_ms: int) -> void:
    if not actions.is_empty() and (actions.size() >= 128 or now_ms - last_flush_ms >= 30000):
        flush(now_ms)

func flush(now_ms: int = -1) -> void:
    if actions.is_empty():
        return
    if now_ms < 0:
        now_ms = Time.get_ticks_msec()
    sequence += 1
    episodes.append({
        "episode_id": session + ":" + str(sequence), "session_id": session, "sequence": sequence,
        "actions": actions.duplicate(true), "coordinate_space": "godot-renderer-xz-metres",
        "world_write_authority": false, "chronological_episode": true,
    })
    actions.clear()
    last_flush_ms = now_ms
    while episodes.size() > 16:
        episodes.pop_front()
        dropped += 1
    var snapshot := {"schema": SCHEMA, "episodes": episodes, "dropped_episodes": dropped}
    var encoded := JSON.stringify(snapshot)
    while encoded.to_utf8_buffer().size() > MAX_BYTES and episodes.size() > 1:
        episodes.pop_front()
        dropped += 1
        snapshot["dropped_episodes"] = dropped
        encoded = JSON.stringify(snapshot)
    if storage.is_empty():
        return
    var file := FileAccess.open(storage + ".tmp", FileAccess.WRITE)
    if file == null:
        push_warning("NOV_EPISODE_SAVE_FAILED open")
        return
    file.store_string(encoded)
    file.flush()
    file.close()
    var error := DirAccess.rename_absolute(storage + ".tmp", storage)
    if error != OK:
        push_warning("NOV_EPISODE_SAVE_FAILED rename=%d" % error)
