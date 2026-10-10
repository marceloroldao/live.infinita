extends RefCounted
# Only eye-confirmed observations enter; no wildlife nodes or physical registry access.
const MAX_MS := 20000
const SIGHT_MS := 1500
const COOLDOWN_MS := 60000
const APPROACHED_M := 6.5
var context_enabled := false
var context_probe := Callable()
var _context_history = preload("res://nov_animal_context_history.gd").new()
var _context_at_start:Dictionary = {}
var _contacts := 0
var _context_error := ""
var _history = preload("res://nov_animal_approach_history.gd").new()
var _boot_wait := false
var _restart_cooldown := false
var enabled := false
var _world := ""
var _last_ms := -1
var _last_end := -COOLDOWN_MS
var _serial := 0
var _session := Crypto.new().generate_random_bytes(8).hex_encode()
var _seen: Dictionary = {}
var _active: Dictionary = {}
var _results: Array = []
var _selection: Dictionary = {}
var _distance := 0.0
var _last_remaining := 0.0
var _previous := Vector3(INF,INF,INF)
func configure(path: String) -> void:
    _history.configure(path)
    if context_enabled:_context_history.configure(path+".context" if not path.is_empty() else "")
    if not _history.ready:enabled=false;return
    _results=_history.records.slice(maxi(0,_history.records.size()-16)).duplicate(true)
    if not _results.is_empty():
        var latest: Dictionary=_results.back()
        _world=latest.world_id
        _restart_cooldown=latest.ended_ms==null
        if not _restart_cooldown:
            _last_ms=int(latest.ended_ms);_last_end=_last_ms;_boot_wait=true
func observe(value: Dictionary) -> void:
    if not enabled or value.get("schema")!="live-infinita-nov-visual-observation/v1" or value.get("source")!="local_physics_eye_sensor" or value.get("observer_entity_id")!="nov" or value.get("world_write_authority")!=false or value.get("absence_claim")!=false:return
    var stamp=value.get("logical_time_ms")
    if typeof(stamp) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(stamp)) or float(stamp)<0 or float(stamp)>1.0e15 or float(stamp)!=floorf(float(stamp)):return
    var world=value.get("world_id")
    if typeof(world)!=TYPE_STRING or world.is_empty() or (not _world.is_empty() and world!=_world):return
    if typeof(value.get("visible_entities"))!=TYPE_ARRAY or value.visible_entities.size()>16:return
    for row in value.visible_entities:
        if typeof(row)!=TYPE_DICTIONARY or row.get("kind")!="rabbit" or row.get("evidence")!="eye_ray_unobstructed":continue
        var id=row.get("entity_id")
        var point=row.get("observed_position_m")
        if typeof(id)!=TYPE_STRING or not id.begins_with(world+":rabbit:") or id.length()>160 or typeof(point)!=TYPE_ARRAY or point.size()!=3:continue
        var valid:=true
        for coordinate in point:
            if typeof(coordinate) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(coordinate)) or absf(float(coordinate))>100000:valid=false
        if not valid:continue
        if _seen.has(id) and int(stamp)<int(_seen[id].stamp):continue
        _seen[id]={"point":Vector3(point[0],point[1],point[2]),"stamp":int(stamp),"world":world,"received":Time.get_ticks_msec()}
    while _seen.size()>16:_seen.erase(_seen.keys()[0])
func finish(reason: String, now: int = -1) -> void:
    _selection.clear()
    if _active.is_empty():return
    var row:=_active.duplicate(true)
    row["ended_ms"]=maxi(_last_ms,now)
    row["result"]=reason
    row["distance_m"]=_distance
    row["contains_prediction"]=false
    row["capture"]=false
    row["absence_claim"]=false
    row["world_write_authority"]=false
    row["approach_confirmed"]=reason=="approached"
    var censored: bool=not reason in ["approached","contact_lost","no_progress","budget_exhausted"]
    var fact: Dictionary={"id":row.id,"world_id":_world,"entity_id":row.entity_id,
        "started_ms":row.started_ms,"ended_ms":row.ended_ms,"result":reason,"distance_m":_distance,
        "initial_observed_remaining_m":row.initial_observed_remaining_m,"final_observed_remaining_m":_last_remaining,"revision":row.revision,
        "censored":censored,"learning_eligible":not censored and _distance>0,
        "capture":false,"contains_prediction":false,"absence_claim":false,"world_write_authority":false}
    var base_stored:=_history.record(fact)
    if not base_stored:enabled=false
    if base_stored and context_enabled and fact.learning_eligible and not _context_at_start.is_empty():
        if not _context_history.record({"approach":fact,"context":_context_at_start,"contacts":_contacts}):
            _context_error="context_checkpoint_failed"
    _context_at_start.clear();_contacts=0
    _results=_history.records.slice(maxi(0,_history.records.size()-16)).duplicate(true)
    print("NOV_ANIMAL_APPROACH_END "+JSON.stringify(row))
    _last_end=int(row.ended_ms);_active.clear();_previous=Vector3(INF,INF,INF)
func _fresh(row: Dictionary, now: int) -> bool:
    return row.world==_world and row.stamp<=now and now-int(row.stamp)<=SIGHT_MS and Time.get_ticks_msec()-int(row.received)<=SIGHT_MS
func choose(current: Vector3, world: String, now: int, resolve: Callable, heading: float=0.0) -> Dictionary:
    _selection.clear()
    if not enabled or not current.is_finite() or world.is_empty() or now<0 or not resolve.is_valid():return {}
    if world!=_world:
        finish("world_changed",now);_seen.clear();_world=world;_last_ms=-1;_last_end=now-COOLDOWN_MS
    if _restart_cooldown:
        _last_end=now;_restart_cooldown=false
    if _boot_wait and now<_last_ms:return {}
    _boot_wait=false
    if now<_last_ms:
        finish("clock_rewind");_seen.clear();return {}
    _last_ms=now
    if not _active.is_empty():
        if _previous.is_finite():_distance+=Vector2(current.x,current.z).distance_to(Vector2(_previous.x,_previous.z))
        _previous=current
        if now>=int(_active.deadline_ms) or Time.get_ticks_msec()-int(_active.wall_started)>=MAX_MS:
            finish("budget_exhausted");return {}
        if not _seen.has(_active.entity_id) or not _fresh(_seen[_active.entity_id],now):
            finish("contact_lost");return {}
    if _active.is_empty():
        if now-_last_end<COOLDOWN_MS:return {}
        var best:=""
        var remaining:=INF
        for id in _seen:
            var seen: Dictionary=_seen[id]
            if not _fresh(seen,now):continue
            var d:=Vector2(current.x,current.z).distance_to(Vector2(seen.point.x,seen.point.z))
            if d>APPROACHED_M and d<=24.0 and d<remaining:best=id;remaining=d
        if best.is_empty():return {}
        _serial+=1;_distance=0.0;_previous=current
        _active={"id":world+":animal-approach:"+_session+":"+str(_serial),"entity_id":best,"arm":"visible",
            "phase":"approach","started_ms":now,"deadline_ms":now+MAX_MS,"wall_started":Time.get_ticks_msec(),
            "scan_started_ms":0,"heading":heading,"base_heading":heading,"revision":0,"updated_ms":now-1000,
            "best_remaining":remaining,"initial_observed_remaining_m":remaining,"world_id":world,"progress_ms":now,"source":"local_physics_eye_sensor","contains_prediction":true}
        _last_remaining=remaining
        _context_at_start={};_contacts=0
        if context_enabled and context_probe.is_valid():
            _context_at_start=context_probe.call(current,_seen[best].point,now)
            if _context_at_start.is_empty():_context_error="context_probe_unavailable"
        if not _history.begin(_active):
            enabled=false;_active.clear();return {}
        print("NOV_ANIMAL_APPROACH_START "+JSON.stringify(_active))
    var seen: Dictionary=_seen[_active.entity_id]
    var point: Vector3=seen.point
    var remaining:=Vector2(current.x,current.z).distance_to(Vector2(point.x,point.z))
    _last_remaining=remaining
    if remaining<=APPROACHED_M and now-int(seen.stamp)<=300 and Time.get_ticks_msec()-int(seen.received)<=500:
        finish("approached");return {}
    if remaining<float(_active.best_remaining)-0.75:_active.best_remaining=remaining;_active.progress_ms=now
    if now-int(_active.progress_ms)>=8000:
        finish("no_progress");return {}
    if not _active.has("goal") or (now-int(_active.updated_ms)>=1000 and Vector2(point.x,point.z).distance_to(Vector2(_active.observed_point[0],_active.observed_point[2]))>=2.0):
        # Stop short of the sighted animal. Destination still passes normal terrain validation.
        var flat:=Vector2(point.x-current.x,point.z-current.z).normalized()
        var requested:=Vector3(point.x-flat.x*5.0,current.y,point.z-flat.y*5.0)
        var resolved: Dictionary=resolve.call(requested)
        var goal: Vector3=resolved.get("position",Vector3(INF,INF,INF))
        if not bool(resolved.get("allowed",false)) or not goal.is_finite() or Vector2(goal.x,goal.z).distance_to(Vector2(requested.x,requested.z))>2.0:
            finish("destination_rejected");return {}
        _active.goal=[goal.x,goal.y,goal.z];_active.observed_point=[point.x,point.y,point.z];_active.updated_ms=now;_active.revision+=1
    _selection=_active.duplicate(true)
    return _selection.duplicate(true)
func observe_movement(value: Dictionary) -> void:
    if _active.is_empty() or not context_enabled:return
    var count=value.get("collisions",0)
    if typeof(count)==TYPE_INT and count>=0:_contacts=mini(10000,_contacts+count)
func status() -> Dictionary:
    return {"enabled":enabled,"active":not _selection.is_empty(),"intent":_selection.duplicate(true),
        "results":_results.duplicate(true),"history":_history.status(),
        "context_history":dict_context_status(),"capture":false,"learned_hunting":false}

func dict_context_status() -> Dictionary:
    var value:Dictionary=_context_history.status()
    value["collection_enabled"]=context_enabled
    value["last_error"]=_context_error
    return value
