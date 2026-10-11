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
var _intent: Dictionary = {}
var _requests: Dictionary = {}
var _busy: Dictionary = {}
var _next_poll := 0

func _ready() -> void:
    for argument in OS.get_cmdline_user_args():
        if str(argument) == "--offline-tour":
            enabled = false
    if OS.has_feature("web"):
        for kind in ["search", "memory", "intent"]:
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
    _intent.clear()
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
    for kind in ["search", "memory", "intent"]:
        var filename := "search-predictions.json" if kind == "search" else ("encounter-memory.json" if kind == "memory" else "search-intent.json")
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
    if data.get("world_id","") != world_id or data.get("world_write_authority",true) != false or data.get("decision_use") != (true if kind == "intent" else false) or data.get("last_error") != null:
        return false
    if kind == "intent":
        if data.get("schema") != "live-infinita-nov-animal-search-intent/v1" or data.get("source") != "native_bounded_animal_search" or data.get("absence_claim") != false or typeof(data.get("active")) != TYPE_BOOL or not _integer(data.get("logical_time_ms")):
            return false
        if float(data.generated_at_unix) < float(_intent.get("generated_at_unix",0)):
            return false
        var selected = data.get("intent")
        if typeof(selected) != TYPE_DICTIONARY:
            return false
        if bool(data.active):
            var contact_search:bool=selected.get("arm")=="contact_search"
            if contact_search:
                if selected.get("phase")!="contact_search" or selected.get("source")!="last_eye_observation_hypothesis" or selected.get("contains_prediction")!=true or selected.get("capture")!=false or selected.get("world_write_authority")!=false or not _integer(selected.get("revision")) or not _integer(selected.get("seed_observed_ms")) or not _integer(selected.get("started_ms")) or selected.seed_observed_ms>selected.started_ms:return false
                if typeof(selected.get("entity_id"))!=TYPE_STRING or not str(selected.entity_id).begins_with(world_id+":rabbit:") or typeof(selected.get("approach_id"))!=TYPE_STRING or not str(selected.approach_id).begins_with(world_id+":animal-approach:") or selected.get("id")!=selected.approach_id+":contact-search":return false
                var seed=selected.get("last_observed_point")
                if typeof(seed)!=TYPE_ARRAY or seed.size()!=3:return false
                for coordinate in seed:
                    if typeof(coordinate) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(coordinate)) or absf(float(coordinate))>100000:return false
            var visible_approach: bool=selected.get("arm")=="visible"
            if visible_approach and (selected.get("source")!="local_physics_eye_sensor" or selected.get("contains_prediction")!=true or selected.get("phase")!="approach" or not _integer(selected.get("revision")) or typeof(selected.get("entity_id"))!=TYPE_STRING or not str(selected.entity_id).begins_with(world_id+":rabbit:")):return false
            if selected.get("arm") not in ["memory","last_seen","visible","contact_search"] or selected.get("phase") not in (["contact_search"] if contact_search else ["approach","scan"]) or typeof(selected.get("id")) != TYPE_STRING or not str(selected.id).begins_with(world_id+(":animal-approach:" if visible_approach or contact_search else ":animal-search:")) or not _integer(selected.get("started_ms")) or not _integer(selected.get("deadline_ms")) or selected.started_ms>data.logical_time_ms or selected.deadline_ms<=selected.started_ms or selected.deadline_ms>selected.started_ms+(5000 if contact_search else (20000 if visible_approach else 45000)):
                return false
            if not _integer(selected.get("scan_started_ms")) or typeof(selected.get("base_heading")) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(selected.base_heading)):
                return false
            if selected.phase=="scan" and (selected.scan_started_ms<selected.started_ms or selected.scan_started_ms>data.logical_time_ms):
                return false
            var goal = selected.get("goal")
            if typeof(goal)!=TYPE_ARRAY or goal.size()!=3 or typeof(selected.get("heading")) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(selected.heading)):
                return false
            for coordinate in goal:
                if typeof(coordinate) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(coordinate)) or absf(float(coordinate))>100000:
                    return false
        _intent={"generated_at_unix":data.generated_at_unix,"active":data.active,"intent":selected.duplicate(true)}
        return true
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
    var approach := intent(now)
    if approach.get("arm")=="contact_search":return first+"\nBusca: voltando ao último ponto observado"
    if approach.get("arm")=="visible":return first+"\nBusca: aproximando-se de coelho avistado"
    if not search_fresh:
        return first+"\nBusca: aguardando dados do servidor"
    first += " | %d regiões" % int(_search.active)
    var selected := intent(now)
    if not selected.is_empty():
        return first+"\nBusca: %s (%s)" % [("observando" if selected.phase=="scan" else "indo à região"),("memória" if selected.arm=="memory" else "último local")]
    if int(_search.paired) > 0:
        return first+"\nAcertos: memória %d/%d | último %d/%d" % [int(_search.memory_hits),int(_search.paired),int(_search.last_seen_hits),int(_search.paired)]
    if int(_search.active) > 0:
        return first+"\nBusca: aguardando novo avistamento"
    if int(_search.pending) > 0:
        return first+"\nBusca: aguardando confirmação"
    return first+"\nBusca: aguardando novos encontros"

func intent(now: float = -1.0, logical_ms: int = -1) -> Dictionary:
    if now<0.0:now=Time.get_unix_time_from_system()
    if not enabled or not bool(_intent.get("active",false)) or not _fresh(_intent,now) or now-float(_intent.get("generated_at_unix",0))>15.0:
        return {}
    var value: Dictionary = _intent.get("intent",{})
    if logical_ms>=0 and (logical_ms>=int(value.get("deadline_ms",0)) or logical_ms+1000<int(value.get("started_ms",0))):
        return {}
    value=value.duplicate(true)
    if logical_ms>=0 and value.get("phase")=="scan":
        value["heading"]=float(value.base_heading)+TAU*clampf(float(logical_ms-int(value.scan_started_ms))/8000.0,0.0,1.0)
    return value
