extends Node
# Read-only presentation: this node never proposes or applies a movement.
const SEARCH_SCHEMA := "live-infinita-nov-animal-search/v1"
const MEMORY_SCHEMA := "live-infinita-nov-animal-memory/v1"
const PUBLIC_ROOT := "/var/www/live-infinita-godot/wildlife/"
const MAX_BYTES := 131072
const FRESH_SECONDS := 60.0
var enabled := true
var world_id := ""
var _search: Dictionary = {}
var _memory: Dictionary = {}
var _requests: Dictionary = {}
var _busy: Dictionary = {}
var _next_poll := 0

func _ready() -> void:
    for argument in OS.get_cmdline_user_args():
        if str(argument) == "--offline-tour":
            enabled = false
    if OS.has_feature("web"):
        for kind in ["search", "memory"]:
            var request := HTTPRequest.new()
            request.timeout = 4.0
            request.body_size_limit = MAX_BYTES
            add_child(request)
            request.request_completed.connect(Callable(self,"_on_response").bind(kind))
            _requests[kind] = request
            _busy[kind] = false

func set_world(value: String) -> void:
    if value == world_id:
        return
    world_id = value
    _search.clear()
    _memory.clear()
    _next_poll = 0

func web_url(path: String, origin: String = "") -> String:
    if origin.is_empty() and OS.has_feature("web"):
        origin = str(JavaScriptBridge.eval("window.location.origin"))
    if not (origin.begins_with("https://") or origin.begins_with("http://")):
        return ""
    return origin.trim_suffix("/") + path

func _process(_delta: float) -> void:
    if not enabled or world_id.is_empty() or Time.get_ticks_msec() < _next_poll:
        return
    _next_poll = Time.get_ticks_msec()+5000
    for kind in ["search", "memory"]:
        var filename := "search-predictions.json" if kind == "search" else "encounter-memory.json"
        if OS.has_feature("web"):
            if bool(_busy.get(kind,false)):
                continue
            var url := web_url("/godot/wildlife/"+filename+"?t="+str(int(Time.get_unix_time_from_system())))
            if url.is_empty():
                continue
            _busy[kind] = true
            if _requests[kind].request(url) != OK:
                _busy[kind] = false
        elif FileAccess.file_exists(PUBLIC_ROOT+filename):
            var file := FileAccess.open(PUBLIC_ROOT+filename,FileAccess.READ)
            if file != null and file.get_length() <= MAX_BYTES:
                _accept(file.get_as_text(),kind)
                file.close()

func _on_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray, kind: String) -> void:
    _busy[kind] = false
    if result == HTTPRequest.RESULT_SUCCESS and code == 200 and body.size() <= MAX_BYTES:
        _accept(body.get_string_from_utf8(),kind)

func _integer(value: Variant, maximum: float = 1.0e15) -> bool:
    return (typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT) and is_finite(float(value)) and float(value) >= 0.0 and float(value) <= maximum and float(value) == floorf(float(value))

func _fresh(data: Dictionary, now: float) -> bool:
    var stamp = data.get("generated_at_unix",null)
    return (typeof(stamp) == TYPE_INT or typeof(stamp) == TYPE_FLOAT) and is_finite(float(stamp)) and float(stamp) <= now+30.0 and now-float(stamp) <= FRESH_SECONDS

func _accept(raw: String, kind: String) -> bool:
    if not enabled or world_id.is_empty() or raw.to_utf8_buffer().size() > MAX_BYTES:
        return false
    var data = JSON.parse_string(raw)
    if typeof(data) != TYPE_DICTIONARY or not _fresh(data,Time.get_unix_time_from_system()):
        return false
    if data.get("world_id","") != world_id or data.get("world_write_authority",true) != false or data.get("decision_use",true) != false or data.get("last_error") != null:
        return false
    if kind == "memory":
        if data.get("schema","") != MEMORY_SCHEMA or not _integer(data.get("stored_and_recovered_encounters")):
            return false
        if float(data.generated_at_unix) < float(_memory.get("generated_at_unix",0)):
            return false
        _memory = {"generated_at_unix":data.generated_at_unix,"stored":int(data.stored_and_recovered_encounters)}
        return true
    if kind != "search" or data.get("schema","") != SEARCH_SCHEMA or data.get("source","") != "verified_recalled_eye_encounters" or data.get("contains_prediction",false) != true or data.get("absence_claim",true) != false:
        return false
    var counters = data.get("counters")
    var forecasts = data.get("forecasts")
    if typeof(counters) != TYPE_DICTIONARY or typeof(forecasts) != TYPE_ARRAY or forecasts.size() > 16 or not _integer(data.get("logical_time_ms")):
        return false
    for key in ["issued","paired","memory_hits","last_seen_hits","expired_without_observation"]:
        if not _integer(counters.get(key)):
            return false
    if counters.paired > counters.issued or counters.memory_hits > counters.paired or counters.last_seen_hits > counters.paired or counters.expired_without_observation+counters.paired > counters.issued:
        return false
    var active := 0
    for forecast in forecasts:
        if typeof(forecast) != TYPE_DICTIONARY or not _integer(forecast.get("issued_ms")) or not _integer(forecast.get("expires_ms")):
            return false
        if forecast.get("contains_prediction",false) != true or float(forecast.issued_ms) > float(data.logical_time_ms) or float(forecast.expires_ms) != float(forecast.issued_ms)+60000.0:
            return false
        if float(forecast.expires_ms) > float(data.logical_time_ms):
            active += 1
    if float(data.generated_at_unix) < float(_search.get("generated_at_unix",0)):
        return false
    _search = {"generated_at_unix":data.generated_at_unix,"active":active,"pending":forecasts.size(),
        "paired":int(counters.paired),"memory_hits":int(counters.memory_hits),"last_seen_hits":int(counters.last_seen_hits)}
    return true

func lines(now: float = -1.0) -> String:
    if not enabled:
        return "Animais: prévia offline"
    if now < 0.0:
        now = Time.get_unix_time_from_system()
    var memory_fresh := _fresh(_memory,now)
    var search_fresh := _fresh(_search,now)
    var first := "Animais: %d lembrados" % int(_memory.stored) if memory_fresh else "Animais: aguardando memória"
    if not search_fresh:
        return first+"\nBusca: aguardando dados do servidor"
    first += " | %d regiões" % int(_search.active)
    if int(_search.paired) > 0:
        return first+"\nAcertos: memória %d/%d | último %d/%d" % [int(_search.memory_hits),int(_search.paired),int(_search.last_seen_hits),int(_search.paired)]
    if int(_search.active) > 0:
        return first+"\nBusca: aguardando novo avistamento"
    if int(_search.pending) > 0:
        return first+"\nBusca: aguardando confirmação"
    return first+"\nBusca: aguardando novos encontros"
