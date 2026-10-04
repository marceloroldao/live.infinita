extends Node
signal snapshot_ready(snapshot: Dictionary)
const PRIVATE_PATH := "/var/lib/live-infinita/memoria-local/navigation-recall.json"
var _request: HTTPRequest
var _next_poll := 0
var _valid_until := 0.0
var enabled := true
func _ready() -> void:
    for argument in OS.get_cmdline_user_args():
        if str(argument) == "--offline-tour":
            enabled = false
    if OS.has_feature("web"):
        _request = HTTPRequest.new()
        _request.timeout = 5.0
        add_child(_request)
        _request.request_completed.connect(_on_response)
func _process(_delta: float) -> void:
    if not enabled:
        return
    var now := Time.get_unix_time_from_system()
    if _valid_until > 0.0 and now > _valid_until:
        _valid_until = 0.0
        snapshot_ready.emit({})
    if Time.get_ticks_msec() < _next_poll:
        return
    _next_poll = Time.get_ticks_msec() + 30000
    if OS.has_feature("web"):
        _request.request("/godot/navigation-memory/recall.json?t=" + str(int(now / 30.0)))
    elif FileAccess.file_exists(PRIVATE_PATH):
        _accept(FileAccess.get_file_as_string(PRIVATE_PATH))
func _on_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if result == HTTPRequest.RESULT_SUCCESS and code == 200 and body.size() <= 2000000:
        _accept(body.get_string_from_utf8())
func _accept(raw: String) -> void:
    if raw.length() > 2000000:
        return
    var data = JSON.parse_string(raw)
    if typeof(data) != TYPE_DICTIONARY:
        return
    var snapshot: Dictionary = data
    var now := Time.get_unix_time_from_system()
    var generated := float(snapshot.get("generated_at_unix", 0.0))
    var rows = snapshot.get("entries", [])
    if str(snapshot.get("schema", "")) != "live-infinita-nov-navigation-recall/v1" or str(snapshot.get("source", "")) != "memoria.ia-local-structural-api":
        return
    if generated > now + 30.0 or now - generated > 180.0 or str(snapshot.get("coordinate_space", "")) != "godot-renderer-xz-metres":
        return
    if snapshot.get("world_write_authority", true) != false or typeof(rows) != TYPE_ARRAY or rows.size() > 4096:
        return
    _valid_until = generated + 180.0
    snapshot_ready.emit(snapshot)
