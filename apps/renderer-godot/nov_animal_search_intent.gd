extends RefCounted
# Native bounded experiment. Only propose goals; normal locomotion owns collision.
const SCHEMA := "live-infinita-nov-animal-search-intent/v1"
const POLICY_SCHEMA := "live-infinita-nov-animal-search-policy/v1"
const CYCLE_MS := 3600000
const COOLDOWN_MS := 300000
const MAX_ATTEMPT_MS := 45000
const SCAN_MS := 8000
const MAX_DISTANCE_M := 40.0
var _approach = preload("res://nov_animal_approach.gd").new()
var enabled := false
var _failed := false
var _world := ""
var _session := ""
var _path := ""
var _public := ""
var _source := ""
var _last_ms := -1
var _last_end := -COOLDOWN_MS
var _cycle := -1
var _cycle_starts := 0
var _serial := 0
var _active: Dictionary = {}
var _results: Array = []
var _counts := {"memory":{"started":0,"confirmed":0,"not_observed":0,"aborted":0},
    "last_seen":{"started":0,"confirmed":0,"not_observed":0,"aborted":0}}
var _forecasts: Array = []
var _next_poll := 0
var _last_publish := -10000
var _restart_pending := false
var _wall_start := 0
var _boot_wait := false

func _integer(value: Variant) -> bool:
    return typeof(value) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(value)) and float(value)>=0 and float(value)<=1.0e15 and float(value)==floorf(float(value))

func _point(value: Variant, size: int) -> bool:
    if typeof(value)!=TYPE_ARRAY or value.size()!=size:return false
    for n in value:
        if typeof(n) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(n)) or absf(float(n))>100000:return false
    return true

func _sealed_read(path: String) -> Dictionary:
    if not FileAccess.file_exists(path):return {}
    var file := FileAccess.open(path,FileAccess.READ)
    if file==null or file.get_length()>100000:return {}
    var envelope = JSON.parse_string(file.get_as_text());file.close()
    if typeof(envelope)!=TYPE_DICTIONARY or typeof(envelope.get("payload"))!=TYPE_STRING or envelope.get("sha256")!=str(envelope.payload).sha256_text():return {}
    var value = JSON.parse_string(envelope.payload)
    return value if typeof(value)==TYPE_DICTIONARY else {}

func configure(state_path: String, public_path: String, source_path: String, session: String) -> void:
    _approach.enabled=OS.get_environment("LIVE_INFINITA_ANIMAL_APPROACH_ENABLED")=="1"
    _approach.configure(state_path+".approach" if not state_path.is_empty() else "")
    _path=state_path;_public=public_path;_source=source_path;_session=session
    enabled=not state_path.is_empty() and not public_path.is_empty() and not source_path.is_empty() and session.length()==32
    if not enabled or not FileAccess.file_exists(_path):return
    var saved := _sealed_read(_path)
    if saved.get("schema")!=POLICY_SCHEMA or typeof(saved.get("world_id"))!=TYPE_STRING or saved.world_id.is_empty() or saved.get("session_id")!=_session or not _integer(saved.get("logical_time_ms")) or not _integer(saved.get("serial")) or not _integer(saved.get("cycle_starts")) or float(saved.cycle_starts)>4 or not _integer(saved.get("cycle")) or typeof(saved.get("active"))!=TYPE_DICTIONARY or typeof(saved.get("results"))!=TYPE_ARRAY or saved.results.size()>16 or typeof(saved.get("counts"))!=TYPE_DICTIONARY:
        _failed=true;return
    var last_end = saved.get("last_end_ms")
    if typeof(last_end) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(last_end)) or float(last_end)<-COOLDOWN_MS or float(last_end)>float(saved.logical_time_ms):
        _failed=true;return
    for arm in ["memory","last_seen"]:
        var count = saved.counts.get(arm)
        if typeof(count)!=TYPE_DICTIONARY:_failed=true;return
        for key in ["started","confirmed","not_observed","aborted"]:
            if not _integer(count.get(key)):_failed=true;return
        if count.confirmed+count.not_observed+count.aborted>count.started:_failed=true;return
    if saved.counts.memory.started+saved.counts.last_seen.started!=saved.serial or saved.cycle_starts>saved.serial:
        _failed=true;return
    var active: Dictionary = saved.active
    if not active.is_empty() and not _valid_active(active,int(saved.logical_time_ms)):
        _failed=true;return
    _world=saved.world_id;_last_ms=int(saved.logical_time_ms);_serial=int(saved.serial)
    _cycle=int(saved.cycle);_cycle_starts=int(saved.cycle_starts);_last_end=int(last_end)
    _active=active;_results=saved.results;_counts=saved.counts
    _restart_pending=not _active.is_empty()
    _boot_wait=true

func _valid_active(value: Dictionary, now: int) -> bool:
    return value.get("arm") in ["memory","last_seen"] and value.get("phase") in ["approach","scan"] and _point(value.get("goal"),3) and _integer(value.get("started_ms")) and _integer(value.get("deadline_ms")) and _integer(value.get("progress_ms")) and _integer(value.get("scan_started_ms")) and value.started_ms<=now and value.deadline_ms>value.started_ms and value.deadline_ms<=value.started_ms+MAX_ATTEMPT_MS and typeof(value.get("entity_id"))==TYPE_STRING and typeof(value.get("id"))==TYPE_STRING and typeof(value.get("forecast_id"))==TYPE_STRING and typeof(value.get("evidence_ids"))==TYPE_ARRAY and value.evidence_ids.size()>=3 and value.evidence_ids.size()<=16 and typeof(value.get("heading")) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(value.heading)) and typeof(value.get("base_heading")) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(value.base_heading)) and typeof(value.get("best_remaining")) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(value.best_remaining)) and float(value.best_remaining)>=0

func _forecast_valid(row: Dictionary, now: int) -> bool:
    if row.get("contains_prediction")!=true or typeof(row.get("entity_id"))!=TYPE_STRING or not str(row.entity_id).begins_with(_world+":rabbit:") or typeof(row.get("forecast_id"))!=TYPE_STRING or str(row.forecast_id).length()!=64 or not _integer(row.get("issued_ms")) or not _integer(row.get("expires_ms")) or row.issued_ms>now or row.expires_ms!=row.issued_ms+60000 or row.expires_ms-now<20000 or not _point(row.get("center_xz_m"),2) or not _point(row.get("last_seen_xz_m"),2) or row.get("radius_m")!=8:
        return false
    var ids = row.get("evidence_ids")
    if typeof(ids)!=TYPE_ARRAY or ids.size()<3 or ids.size()>16:return false
    var distinct := {}
    for identity in ids:
        if typeof(identity)!=TYPE_STRING or not str(identity).begins_with("structural-event:") or distinct.has(identity):return false
        distinct[identity]=true
    return true

func _poll(now: int) -> void:
    if Time.get_ticks_msec()<_next_poll:return
    _next_poll=Time.get_ticks_msec()+5000
    _forecasts.clear()
    if not FileAccess.file_exists(_source) or Time.get_unix_time_from_system()-FileAccess.get_modified_time(_source)>20:return
    var saved := _sealed_read(_source)
    if saved.get("schema")!="live-infinita-nov-animal-search/v1" or saved.get("world_id")!=_world or saved.get("session_id")!=_session or not _integer(saved.get("logical_time_ms")) or saved.logical_time_ms>now+1000 or now-saved.logical_time_ms>15000 or typeof(saved.get("pending"))!=TYPE_ARRAY or saved.pending.size()>16:return
    for row in saved.pending:
        if typeof(row)==TYPE_DICTIONARY and _forecast_valid(row,now):_forecasts.append(row.duplicate(true))

func _write(path: String, value: Dictionary, private: bool) -> bool:
    var raw := JSON.stringify(value)
    var file := FileAccess.open(path+".tmp",FileAccess.WRITE)
    if file==null:return false
    file.store_string(JSON.stringify({"payload":raw,"sha256":raw.sha256_text()}) if private else raw)
    file.flush();file.close()
    return FileAccess.set_unix_permissions(path+".tmp",384 if private else 420)==OK and DirAccess.rename_absolute(path+".tmp",path)==OK

func save(force: bool = false) -> bool:
    if not enabled or _path.is_empty() or _world.is_empty() or _last_ms<0:return true
    if not force and Time.get_ticks_msec()-_last_publish<1000:return true
    var saved := {"schema":POLICY_SCHEMA,"world_id":_world,"session_id":_session,"logical_time_ms":_last_ms,
        "serial":_serial,"cycle":_cycle,"cycle_starts":_cycle_starts,"last_end_ms":_last_end,
        "active":_active,"results":_results,"counts":_counts}
    if not _write(_path,saved,true):_failed=true;return false
    var approach: Dictionary=_approach.status()
    var selected: Dictionary=approach.intent if approach.active else _active
    var public := {"schema":SCHEMA,"world_id":_world,"generated_at_unix":Time.get_unix_time_from_system(),
        "logical_time_ms":_last_ms,"source":"native_bounded_animal_search","world_write_authority":false,
        "decision_use":true,"absence_claim":false,"active":not selected.is_empty(),"approach":approach,
        "intent":selected,"counts":_counts,"results":_results,"cooldown_ms":COOLDOWN_MS,
        "attempt_budget_ms":MAX_ATTEMPT_MS,"cycle_attempt_limit":4,"last_error":"search_policy_unavailable" if _failed else null}
    if not _write(_public,public,false):_failed=true;return false
    _last_publish=Time.get_ticks_msec()
    return true

func finish(reason: String, confirmed: bool = false, stamp: int = -1) -> void:
    var had_approach: bool=not _approach._active.is_empty()
    _approach.finish(reason,stamp)
    if _active.is_empty():
        if had_approach:save(true)
        return
    var row := _active.duplicate(true)
    _last_ms=maxi(_last_ms,stamp)
    var end := _last_ms
    row["ended_ms"]=end;row["result"]=reason;row["confirmed_by_eye_sensor"]=confirmed
    row["absence_claim"]=false
    var arm := str(row.arm)
    _counts[arm]["confirmed" if confirmed else ("not_observed" if reason=="not_observed_within_budget" else "aborted")]+=1
    _results.append(row)
    while _results.size()>16:_results.pop_front()
    _active.clear();_last_end=end
    save(true)
    print("NOV_ANIMAL_SEARCH_END arm=%s result=%s confirmed=%s" % [arm,reason,confirmed])

func suspend(reason: String) -> void:
    finish(reason)
    _boot_wait=true

func observe(value: Dictionary) -> void:
    if enabled and not _failed:_approach.observe(value)
    if not enabled or _failed or _active.is_empty() or value.get("schema")!="live-infinita-nov-visual-observation/v1" or value.get("source")!="local_physics_eye_sensor" or value.get("observer_entity_id")!="nov" or value.get("world_id")!=_world or value.get("world_write_authority")!=false or value.get("absence_claim")!=false or not _integer(value.get("logical_time_ms")) or value.logical_time_ms<=_active.started_ms or value.logical_time_ms>_active.deadline_ms or value.logical_time_ms<_last_ms or typeof(value.get("visible_entities"))!=TYPE_ARRAY:
        return
    for seen in value.visible_entities:
        if typeof(seen)==TYPE_DICTIONARY and seen.get("entity_id")==_active.entity_id and seen.get("kind")=="rabbit" and seen.get("evidence")=="eye_ray_unobstructed" and _point(seen.get("observed_position_m"),3):
            finish("animal_seen",true,int(value.logical_time_ms))
            return

func choose(current: Vector3, world: String, now: int, normal_finished: bool, resolve: Callable, visible: Dictionary = {}, heading: float = 0.0) -> Dictionary:
    if not enabled or _failed or world.is_empty() or now<0 or not current.is_finite():return {}
    if not _world.is_empty() and _world!=world:
        _failed=true;return {}
    _world=world
    if now<_last_ms and _boot_wait:return {}
    _boot_wait=false
    if now<_last_ms:
        finish("clock_rewind");_failed=true;save(true);return {}
    _last_ms=now
    if _active.is_empty():
        var approach: Dictionary=_approach.choose(current,world,now,resolve,heading)
        if not approach.is_empty():
            save()
            return approach
    if _restart_pending:
        _restart_pending=false;finish("renderer_restart")
    var cycle := floori(float(now)/CYCLE_MS)
    if cycle!=_cycle:_cycle=cycle;_cycle_starts=0
    if not _active.is_empty():
        var remaining := Vector2(current.x,current.z).distance_to(Vector2(_active.goal[0],_active.goal[2]))
        if _wall_start>0 and Time.get_ticks_msec()-_wall_start>=60000:
            finish("clock_stalled")
        elif now>=int(_active.deadline_ms):
            finish("not_observed_within_budget")
        elif _active.phase=="approach" and now-int(_active.progress_ms)>=15000:
            finish("no_progress")
        else:
            if remaining<float(_active.best_remaining)-0.75:
                _active.best_remaining=remaining;_active.progress_ms=now
            if _active.phase=="approach" and remaining<=2.0:
                _active.phase="scan";_active.goal=[current.x,current.y,current.z];_active.scan_started_ms=now
                _active.base_heading=heading
            if _active.phase=="scan":
                _active.heading=float(_active.base_heading)+TAU*float(now-int(_active.scan_started_ms))/SCAN_MS
                if now-int(_active.scan_started_ms)>=SCAN_MS:finish("not_observed_within_budget")
    if _active.is_empty() and normal_finished and _cycle_starts<4 and now-_last_end>=COOLDOWN_MS and resolve.is_valid():
        _poll(now)
        var arm := "memory" if _serial%2==0 else "last_seen"
        for forecast in _forecasts:
            if not _forecast_valid(forecast,now):continue
            var already_seen := false
            if visible.get("world_id")==world and visible.get("source")=="local_physics_eye_sensor" and typeof(visible.get("visible_entities"))==TYPE_ARRAY and now-int(visible.get("logical_time_ms",-10000))<=1000:
                for seen in visible.visible_entities:
                    if typeof(seen)==TYPE_DICTIONARY and seen.get("entity_id")==forecast.entity_id:already_seen=true
            if already_seen:continue
            var position: Array = forecast.center_xz_m if arm=="memory" else forecast.last_seen_xz_m
            var requested := Vector3(position[0],current.y,position[1])
            if Vector2(current.x,current.z).distance_to(Vector2(requested.x,requested.z))>MAX_DISTANCE_M:continue
            var resolved: Dictionary = resolve.call(requested)
            var goal: Vector3 = resolved.get("position",Vector3(INF,INF,INF))
            if not bool(resolved.get("allowed",false)) or not goal.is_finite() or Vector2(goal.x,goal.z).distance_to(Vector2(requested.x,requested.z))>4.0 or Vector2(current.x,current.z).distance_to(Vector2(goal.x,goal.z))>MAX_DISTANCE_M:continue
            _serial+=1;_cycle_starts+=1;_counts[arm].started+=1
            _wall_start=Time.get_ticks_msec()
            _active={"id":world+":animal-search:"+str(_serial),"arm":arm,"entity_id":forecast.entity_id,
                "forecast_id":forecast.forecast_id,"evidence_ids":forecast.evidence_ids.duplicate(),
                "goal":[goal.x,goal.y,goal.z],"started_ms":now,"deadline_ms":mini(now+MAX_ATTEMPT_MS,int(forecast.expires_ms)),
                "phase":"approach","progress_ms":now,"best_remaining":current.distance_to(goal),
                "scan_started_ms":0,"heading":heading,"base_heading":heading}
            if not save(true):_active.clear();return {}
            print("NOV_ANIMAL_SEARCH_START arm=%s entity=%s region=(%.1f,%.1f)" % [arm,forecast.entity_id,goal.x,goal.z])
            break
    save()
    return _active.duplicate(true)
