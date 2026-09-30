extends RefCounted
# Optional observer-only client. No application-level outbound messages.
const NovProjection = preload("res://nov_map_projection.gd")
const MAX_MESSAGES_PER_FRAME := 12
const STALE_AFTER_MS := 15000
const RECONNECT_MS := 4000

var _projection: RefCounted
var _socket := WebSocketPeer.new()
var _url := ""
var _reconnect_at := 0
var _last_seen_ms := 0
var _has_pose := false
var _visual := Vector2.ZERO
var _region := ""
var _sequence := -1
var _state := "desconectado"

func _init(mapping: Dictionary) -> void:
    _projection = NovProjection.new(mapping)

func start(url: String) -> void:
    _url = url
    _connect()

func _connect() -> void:
    if _url.is_empty():
        _state = "sem_endpoint"
        return
    _socket = WebSocketPeer.new()
    var error := _socket.connect_to_url(_url)
    _state = "aguardando_nov" if error == OK else "conexao_falhou"
    _reconnect_at = Time.get_ticks_msec() + RECONNECT_MS

func poll() -> Dictionary:
    var now := Time.get_ticks_msec()
    _socket.poll()
    match _socket.get_ready_state():
        WebSocketPeer.STATE_OPEN:
            var count := 0
            while _socket.get_available_packet_count() > 0 and count < MAX_MESSAGES_PER_FRAME:
                count += 1
                var raw = JSON.parse_string(_socket.get_packet().get_string_from_utf8())
                if typeof(raw) != TYPE_DICTIONARY:
                    continue
                var value: Dictionary = _projection.project(raw)
                if value.get("ok") == true:
                    _visual = value["position"]
                    _region = str(value["region_id"])
                    _sequence = int(value["sequence"])
                    _last_seen_ms = now
                    _has_pose = true
                    _state = "nov_real_read_only"
        WebSocketPeer.STATE_CLOSED:
            if now >= _reconnect_at:
                _connect()
            else:
                _state = "reconectando"
        _:
            pass
    if _has_pose and now - _last_seen_ms > STALE_AFTER_MS:
        _state = "pose_desatualizada"
    return {"has_pose": _has_pose, "position": _visual, "region_id": _region,
            "sequence": _sequence, "fresh": _has_pose and now - _last_seen_ms <= STALE_AFTER_MS,
            "status": _state, "read_only": true}
