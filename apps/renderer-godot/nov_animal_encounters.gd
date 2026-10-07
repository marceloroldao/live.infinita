extends RefCounted
# Only the ray sensor calls this observer; never reads the wildlife projection.
const SCHEMA := "live-infinita-nov-animal-encounters/v1"
const ACK_SCHEMA := "live-infinita-nov-animal-memory-ack/v1"
const MAX_PENDING := 128
var _path := ""
var _ack_path := ""
var _world := ""
var _session := ""
var _next := 1
var _acked := 0
var _active: Dictionary = {}
var _pending: Array = []
var _last_ms := -1
var _last_save := -10000
var _dropped := 0
var _failed := false
var _restart_pending := false

func _json(raw: String) -> Variant:
    var parser := JSON.new()
    return parser.data if parser.parse(raw)==OK else null

func configure(path: String, ack_path: String) -> void:
    _path = path;_ack_path = ack_path
    _session = Crypto.new().generate_random_bytes(16).hex_encode()
    if path.is_empty() or not FileAccess.file_exists(path):return
    if FileAccess.get_file_as_bytes(path).size()>1000000:_failed = true;return
    var envelope = _json(FileAccess.get_file_as_string(path))
    if typeof(envelope)!=TYPE_DICTIONARY or typeof(envelope.get("payload"))!=TYPE_STRING or envelope.get("sha256")!=str(envelope["payload"]).sha256_text():_failed = true;return
    var value = _json(envelope["payload"])
    if typeof(value)!=TYPE_DICTIONARY or value.get("schema")!=SCHEMA or typeof(value.get("active"))!=TYPE_DICTIONARY or typeof(value.get("pending"))!=TYPE_ARRAY or value["pending"].size()>MAX_PENDING or value["active"].size()>16:_failed = true;return
    _world = str(value.get("world_id",""));_session = str(value.get("session_id",""))
    _next = int(value.get("next_sequence",1));_acked = int(value.get("acknowledged_sequence",0))
    _last_ms = int(value.get("logical_time_ms",-1));_dropped = int(value.get("dropped_samples",0))
    _active = value["active"]
    _pending = value["pending"]
    if _session.length()!=32 or _world.is_empty() or _next<1 or _acked<0 or _acked>=_next or _last_ms<0:
        _failed = true;return
    _restart_pending = true

func _ack() -> void:
    if _ack_path.is_empty() or not FileAccess.file_exists(_ack_path):return
    var value = _json(FileAccess.get_file_as_string(_ack_path))
    if typeof(value)!=TYPE_DICTIONARY or value.get("schema")!=ACK_SCHEMA or value.get("world_id")!=_world or value.get("session_id")!=_session:return
    var n = value.get("cursor")
    if typeof(n) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(n)) or float(n)!=floor(float(n)):return
    var cursor := int(n)
    # Python ack uses a separate payload string for byte-identical checksum.
    if typeof(value.get("proof_payload"))!=TYPE_STRING or value.get("checksum")!=str(value["proof_payload"]).sha256_text():return
    var proof = _json(value["proof_payload"])
    if typeof(proof)!=TYPE_DICTIONARY or proof.get("cursor")!=cursor or proof.get("world_id")!=_world or proof.get("session_id")!=_session:return
    if cursor<_acked or cursor>=_next:return
    _acked = cursor
    while not _pending.is_empty() and int(_pending[0]["sequence"])<=cursor:_pending.pop_front()

func _seal(identity: String, reason: String) -> bool:
    if _pending.size()>=MAX_PENDING:return false
    var row: Dictionary = _active[identity].duplicate(true)
    row["sequence"] = _next;row["closed_reason"] = reason
    _next += 1;_pending.append(row);_active.erase(identity)
    return true

func point_valid(value: Variant) -> bool:
    if typeof(value)!=TYPE_ARRAY or value.size()!=3:return false
    for n in value:
        if typeof(n) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(n)) or absf(float(n))>100000:return false
    return true

func observe(value: Dictionary) -> void:
    if _path.is_empty() or _failed:return
    if value.get("schema")!="live-infinita-nov-visual-observation/v1" or value.get("source")!="local_physics_eye_sensor" or value.get("observer_entity_id")!="nov" or value.get("absence_claim")!=false or value.get("world_write_authority")!=false:return
    var world := str(value.get("world_id",""))
    var stamp = value.get("logical_time_ms")
    if world.is_empty() or typeof(stamp) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(stamp)) or float(stamp)!=floor(float(stamp)) or float(stamp)<0 or not point_valid(value.get("eye_position_m")):return
    var ms := int(stamp)
    if not _world.is_empty() and _world!=world:return
    if ms<_last_ms:return
    var reach = value.get("range_m")
    if typeof(reach) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(reach)) or float(reach)<12 or float(reach)>24:return
    var seen = value.get("visible_entities")
    if typeof(seen)!=TYPE_ARRAY or seen.size()>16:return
    for row in seen:
        if typeof(row)!=TYPE_DICTIONARY or row.get("kind")!="rabbit" or row.get("evidence")!="eye_ray_unobstructed" or typeof(row.get("entity_id"))!=TYPE_STRING or not str(row["entity_id"]).begins_with(world+":rabbit:") or str(row["entity_id"]).length()>200 or not point_valid(row.get("observed_position_m")):return
        var d = row.get("distance_m")
        if typeof(d) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(d)) or float(d)<0.05 or float(d)>float(reach):return
        var eye := Vector3(value["eye_position_m"][0],value["eye_position_m"][1],value["eye_position_m"][2])
        var target := Vector3(row["observed_position_m"][0],row["observed_position_m"][1],row["observed_position_m"][2])
        if absf(eye.distance_to(target)-float(d))>0.01:return
    if _world.is_empty():
        _world = world
        print("NOV_ENCOUNTER_RECORDER_ACTIVE world=%s" % world)
    _ack()
    if _restart_pending:
        for identity in _active.keys():
            if not _seal(identity,"renderer_restart"):_dropped += 1
        _restart_pending = false
    if ms==_last_ms:
        save();return
    _last_ms = ms
    var visible: Dictionary = {}
    for row in seen:visible[row["entity_id"]] = row
    for identity in _active.keys():
        var old: Dictionary = _active[identity]
        if ms-int(old["first_seen_ms"])>=30000 or (not visible.has(identity) and ms-int(old["last_seen_ms"])>=3000):
            _seal(identity,"window_complete" if visible.has(identity) else "lost_visual_contact")
    if _pending.size()>=MAX_PENDING:
        _dropped += seen.size();save();return
    for identity in visible:
        var row: Dictionary = visible[identity]
        if not _active.has(identity):
            _active[identity] = {"entity_id":identity,"kind":"rabbit","first_seen_ms":ms,"last_seen_ms":ms,
                "first_observer_eye_m":value["eye_position_m"].duplicate(),"last_observer_eye_m":value["eye_position_m"].duplicate(),
                "first_target_m":row["observed_position_m"].duplicate(),"last_target_m":row["observed_position_m"].duplicate(),
                "sample_count":1,"min_distance_m":row["distance_m"],"max_distance_m":row["distance_m"],
                "first_range_m":value.get("range_m",24),"last_range_m":value.get("range_m",24)}
        else:
            var encounter: Dictionary = _active[identity]
            encounter["last_seen_ms"] = ms;encounter["sample_count"] = int(encounter["sample_count"])+1
            encounter["last_observer_eye_m"] = value["eye_position_m"].duplicate()
            encounter["last_target_m"] = row["observed_position_m"].duplicate()
            encounter["last_range_m"] = value.get("range_m",24)
            encounter["min_distance_m"] = minf(encounter["min_distance_m"],row["distance_m"])
            encounter["max_distance_m"] = maxf(encounter["max_distance_m"],row["distance_m"])
    save()

func snapshot() -> Dictionary:
    return {"schema":SCHEMA,"world_id":_world,"session_id":_session,"next_sequence":_next,
        "acknowledged_sequence":_acked,"logical_time_ms":_last_ms,"generated_at_unix":Time.get_unix_time_from_system(),
        "pending":_pending.duplicate(true),"active":_active.duplicate(true),"dropped_samples":_dropped,
        "source":"local_physics_eye_sensor","world_write_authority":false,"contains_prediction":false,"absence_claim":false}

func save(force: bool = false) -> bool:
    if _path.is_empty():return true
    if not force and Time.get_ticks_msec()-_last_save<1000:return true
    var payload := JSON.stringify(snapshot())
    var file := FileAccess.open(_path+".tmp",FileAccess.WRITE)
    if file==null:_failed = true;push_warning("NOV_ENCOUNTER_SAVE_FAILED");return false
    file.store_string(JSON.stringify({"payload":payload,"sha256":payload.sha256_text()}));file.flush();file.close()
    if FileAccess.set_unix_permissions(_path+".tmp",384)!=OK or DirAccess.rename_absolute(_path+".tmp",_path)!=OK:
        _failed = true;push_warning("NOV_ENCOUNTER_SAVE_FAILED");return false
    _last_save = Time.get_ticks_msec();return true
