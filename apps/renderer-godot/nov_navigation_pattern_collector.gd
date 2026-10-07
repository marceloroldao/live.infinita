extends RefCounted
const Patterns = preload("res://nov_navigation_patterns.gd")
const SCHEMA := "live-infinita-native-pattern-outcomes/v2"
const PROFILE := "capsule044-height18-lookahead3-contour64-localexit-v3"
const RECALL_PATH := "/var/lib/live-infinita/memoria-local/navigation-pattern-recall-008ej.json"
var patterns = Patterns.new()
var storage := "user://nov-navigation-patterns-008ej.json"
var world_id := ""
var enabled := false
var session := Crypto.new().generate_random_bytes(16).hex_encode()
var local_rows: Array[Dictionary] = []
var recovered_rows: Array[Dictionary] = []
var pending: Dictionary = {}
var journey: RefCounted
var _next_poll := 0
var _valid_until := 0.0
var observed := 0
var changed_decisions := 0
var core_changed_decisions := 0
var exploration_decisions := 0
var exclusions: Dictionary = {}
var closed_contacts: Array[String] = []
func _init(value: RefCounted=null, path: String="user://nov-navigation-patterns-008ej.json") -> void:
    journey=value;storage=path
    if storage.is_empty() or OS.has_feature("web") or OS.get_cmdline_user_args().has("--offline-tour"):return
    load_state()
func load_state() -> void:
    if storage.is_empty() or not FileAccess.file_exists(storage):return
    var file:=FileAccess.open(storage,FileAccess.READ)
    if file==null or file.get_length()>1000000:return
    var parsed=JSON.parse_string(file.get_as_text())
    if typeof(parsed)!=TYPE_DICTIONARY or parsed.get("schema")!=SCHEMA or parsed.get("profile")!=PROFILE or typeof(parsed.get("rows"))!=TYPE_ARRAY or parsed.rows.size()>512:return
    var validator=Patterns.new()
    var accepted: Array[Dictionary]=[]
    for row in parsed.rows:
        if typeof(row)!=TYPE_DICTIONARY or not _valid_row(row) or not validator.observe_attempt(row):return
        accepted.append(row.duplicate(true))
    local_rows=accepted
func _valid_row(row: Dictionary) -> bool:
    var world:=str(row.get("world_id",""))
    return not world.is_empty() and row.get("profile")==PROFILE and row.get("observer")=="nov" and str(row.get("context","")).begins_with(PROFILE+"|"+world+"|local-clear-v1:") and row.get("contains_prediction",true)==false and row.get("physical_attempt",false)==true
func set_context(value: Dictionary) -> void:
    var world:=str(value.get("world_id",""))
    if value.get("observer_entity_id","nov")!="nov":world=""
    if world!=world_id:
        for id in pending.keys():_exclude("world_changed",str(id))
        world_id=world;recovered_rows.clear();_valid_until=0;_next_poll=0
        _rebuild()
func set_enabled(value: bool) -> void:
    var next_enabled:=value and not world_id.is_empty()
    if enabled==next_enabled:return
    enabled=next_enabled
    patterns.enabled=enabled
    if enabled and not storage.is_empty() and not FileAccess.file_exists(storage):_save()
func context(current: Vector2, goal: Vector2, rows: Array[Dictionary]) -> String:
    if not enabled:return ""
    return PROFILE+"|"+world_id+"|"+patterns.context(current,goal,rows)
func recommend(key: String) -> Dictionary:
    if not enabled:return {}
    var result: Dictionary=patterns.recommend(key)
    if not result.is_empty():return result
    var counts: Dictionary={-1:0,1:0}
    for row in patterns.records:
        if row.context==key:counts[int(row.side)]+=1
    # At most four measured attempts per unseen signature bootstrap both sides.
    # Unfinished/censored runs grant no outcome credit.
    var total: int=counts[-1]+counts[1]
    if total==0 or total>=4 or (counts[-1]>=2 and counts[1]>=2):return {}
    var side := -1 if int(counts[-1])<int(counts[1]) else 1
    return {"side":side,"context":key,"source":"pattern-exploration",
        "observation_ids":[],"contains_prediction":true}
func _exclude(reason: String, id: String) -> void:
    var metadata: Dictionary=pending.get(id,{})
    pending.erase(id)
    exclusions[reason]=int(exclusions.get(reason,0))+1
    print("NOV_PATTERN_EXCLUDED "+JSON.stringify({"reason":reason,"contact_id":id,"world_id":world_id,
        "goal_id":metadata.get("goal_id","")}))
func _close(id: String) -> void:
    pending.erase(id)
    closed_contacts.append(id)
    while closed_contacts.size()>64:closed_contacts.pop_front()
func _record(id: String, outcome: String, basis: String, total_distance: float, ended: float, progress: float=0.0) -> void:
    var metadata: Dictionary=pending.get(id,{})
    if metadata.is_empty():return
    var row: Dictionary={"attempt_id":id,"world_id":world_id,"observer":"nov","profile":PROFILE,
        "context":metadata.context,"side":metadata.side,"outcome":outcome,
        "distance_m":maxf(0.0,total_distance-float(metadata.distance_base)),
        "initial_remaining_m":metadata.initial_remaining_m,"physical_attempt":true,"contains_prediction":false,
        "ended_at_unix":ended,"exploration":metadata.exploration,
        "completion_basis":basis,"exit_progress_m":progress}
    if not patterns.observe_attempt(row):_exclude("invalid_measured_record",id);return
    local_rows.append(row)
    while local_rows.size()>512:local_rows.pop_front()
    observed+=1
    _close(id);_save()
    print("NOV_PATTERN_OUTCOME "+JSON.stringify(row))
func observe_action(action: Dictionary) -> void:
    if not enabled or journey==null or not bool(action.get("physical_attempt",false)):return
    if action.get("route_goal_id","")!=journey.identity or action.get("context_start",{}).get("world_id","")!=world_id:return
    # Only completed actual swept movement may seed or finish a local contact.
    # A pre-execution validation rejection does not become a physical failure.
    if not bool(action.get("executed_motion",false)):return
    var outcome:=str(action.get("outcome",""))
    if not outcome in ["step_reached","goal_reached","blocked"]:return
    var frame: Dictionary=action.get("perception",{}).get("contour",{})
    var serial:=int(frame.get("contact_serial",0))
    var id: String=session+":"+str(journey.identity)+":"+str(serial)
    var key:=str(frame.get("pattern_context",""))
    if bool(frame.get("active",false)) and not key.is_empty() and frame.get("initial_side",0) in [-1,1] and not closed_contacts.has(id):
        for previous in pending.keys():
            if previous!=id:_exclude("new_contact_before_executed_exit",str(previous))
        if not pending.has(id):
            var start: Array=action.get("start",[])
            var goal: Array=action.get("goal",[])
            if start.size()!=2 or goal.size()!=2:return
            var remaining:=Vector2(start[0],start[1]).distance_to(Vector2(goal[0],goal[1]))
            var recommendation: Dictionary=frame.get("pattern_recommendation",{})
            pending[id]={"goal_id":str(journey.identity),"context":key,"side":int(frame.initial_side),
                "contact_serial":serial,"waiting_exit":false,
                "distance_base":maxf(0.0,journey.distance_m-journey.pending_m),"initial_remaining_m":remaining,
                "exploration":recommendation.get("source","")=="pattern-exploration"}
            if recommendation.get("source","")=="pattern-exploration":exploration_decisions+=1
            elif bool(frame.get("pattern_changed_initial_side",false)):
                changed_decisions+=1
                if recommendation.get("source","")=="recovered-pattern-evidence":core_changed_decisions+=1
            print("NOV_PATTERN_DECISION "+JSON.stringify({"world_id":world_id,"goal_id":journey.identity,
                "contact_id":id,"context":key,"side":frame.initial_side,"default_side":frame.get("default_side",0),
                "source":recommendation.get("source","perception"),"observation_ids":recommendation.get("observation_ids",[]),
                "changed_initial_side":frame.get("pattern_changed_initial_side",false),"contains_prediction":true}))
    var proposal: Dictionary=frame.get("exit_proposal",{})
    if not proposal.is_empty():
        var exit_id: String=session+":"+str(journey.identity)+":"+str(proposal.get("contact_serial",0))
        if pending.has(exit_id):
            var start: Array=proposal.get("start",[])
            var normal: Array=proposal.get("normal",[])
            if start.size()==2 and normal.size()==2:
                pending[exit_id].waiting_exit=true
                pending[exit_id].exit_start=Vector2(start[0],start[1])
                pending[exit_id].exit_normal=Vector2(normal[0],normal[1]).normalized()
    for current_id in pending.keys():
        var metadata: Dictionary=pending[current_id]
        if metadata.goal_id!=str(journey.identity):continue
        if outcome=="blocked" and int(action.get("collisions",0))>0:
            _record(str(current_id),"blocked","physical_collision",journey.distance_m,float(action.ended_at_unix))
        elif outcome in ["step_reached","goal_reached"] and bool(metadata.waiting_exit) and int(action.get("collisions",0))==0:
            var end: Array=action.get("end",[])
            if end.size()!=2:continue
            var progress: float=(Vector2(end[0],end[1])-Vector2(metadata.exit_start)).dot(Vector2(metadata.exit_normal))
            if progress>=0.75:
                _record(str(current_id),"contour_completed","executed_exit",journey.distance_m,float(action.ended_at_unix),progress)
func finish_attempt(attempt: Dictionary) -> void:
    for id in pending.keys():
        var metadata: Dictionary=pending[id]
        if metadata.goal_id!=str(attempt.get("goal_id","")):continue
        var outcome:=str(attempt.get("termination",""))
        if not enabled or attempt.get("world_id","")!=world_id:_exclude("scope_or_disabled",str(id));continue
        if int(attempt.get("completed_steps",0))+int(attempt.get("blocked_attempts",0))<=0:_exclude("no_executed_action",str(id));continue
        if outcome=="arrived" and bool(attempt.get("quality_eligible",false)):
            _record(str(id),"contour_completed","goal_reached",float(attempt.distance_m),float(attempt.ended_at_unix))
        elif outcome=="stuck_recovery":
            _record(str(id),"stuck_recovery","stuck_recovery",float(attempt.distance_m),float(attempt.ended_at_unix))
        else:_exclude(outcome if not outcome.is_empty() else "unknown_terminal",str(id))
func _save() -> void:
    if storage.is_empty() or OS.has_feature("web"):return
    var file:=FileAccess.open(storage+".tmp",FileAccess.WRITE)
    if file==null:push_warning("NOV_PATTERN_SAVE_FAILED");return
    file.store_string(JSON.stringify({"schema":SCHEMA,"world_id":world_id,"profile":PROFILE,"rows":local_rows}))
    file.flush();file.close()
    if DirAccess.rename_absolute(storage+".tmp",storage)!=OK:push_warning("NOV_PATTERN_RENAME_FAILED")
func _rebuild() -> void:
    patterns.records.clear();patterns._identities.clear()
    var merged: Dictionary={}
    for row in local_rows:
        if row.world_id==world_id:merged[str(row.attempt_id)]=row.duplicate(true)
    for row in recovered_rows:
        var local: Dictionary=merged.get(str(row.attempt_id),{})
        var fact:=row.duplicate(true);fact.erase("observation_id")
        if local.is_empty() or local==fact:merged[str(row.attempt_id)]=row.duplicate(true)
    var rows: Array=merged.values()
    rows.sort_custom(func(a,b):return float(a.ended_at_unix)<float(b.ended_at_unix))
    for row in rows:patterns.observe_attempt(row)
func accept_recall(data: Dictionary, now: float) -> bool:
    if data.get("schema")!="live-infinita-native-pattern-recall/v2" or data.get("world_id")!=world_id or data.get("world_write_authority",true)!=false:return false
    var generated:=float(data.get("generated_at_unix",0))
    if not is_finite(generated) or generated>now+30 or now-generated>180:return false
    var rows=data.get("entries",[])
    if typeof(rows)!=TYPE_ARRAY or rows.size()>512:return false
    var validated: Array[Dictionary]=[]
    for row in rows:
        if typeof(row)!=TYPE_DICTIONARY or not _valid_row(row) or row.get("world_id")!=world_id:return false
        var observation:=str(row.get("observation_id",""))
        if not observation.begins_with("structural-event:") or observation.length()!=57:return false
        var check_memory=Patterns.new()
        if not check_memory.observe_attempt(row):return false
        validated.append(row.duplicate(true))
    recovered_rows=validated;_valid_until=generated+180;_rebuild()
    return true
func poll(now: float) -> void:
    if not enabled:return
    if _valid_until>0 and now>_valid_until:
        recovered_rows.clear();_valid_until=0;_rebuild()
    if Time.get_ticks_msec()<_next_poll:return
    _next_poll=Time.get_ticks_msec()+30000
    if FileAccess.file_exists(RECALL_PATH):
        var file:=FileAccess.open(RECALL_PATH,FileAccess.READ)
        if file!=null and file.get_length()<=1000000:
            var data=JSON.parse_string(file.get_as_text())
            if typeof(data)==TYPE_DICTIONARY:accept_recall(data,now)
func status() -> Dictionary:
    return {"observed_outcomes":observed,"ram_records":local_rows.size(),"recovered_records":recovered_rows.size(),
        "changed_initial_decisions":changed_decisions,"core_changed_initial_decisions":core_changed_decisions,
        "exploration_decisions":exploration_decisions,"enabled":enabled,
        "pending_contacts":pending.size(),"exclusions":exclusions.duplicate()}
