extends RefCounted
signal attempt_finished(attempt: Dictionary)
var pattern_status: Callable
# Complete physical journeys, independent of recorder flush windows.
const LIMIT := 4096
var memory: RefCounted
var identity := ""
var world_id := ""
var goal := Vector2.ZERO
var steps: Array = []
var pending_m := 0.0
var distance_m := 0.0
var closed := true
var valid := true
var arrivals := 0
var interruptions := 0
var recoveries := 0
var blocked_attempts := 0
var completed_steps := 0
var last_serial := 0
var saved_at := -10000
var causal_ram_steps := 0
var causal_memoria_steps := 0
var last_result := "aguardando caminhada"
var motion_state := "idle"
var last_reason := ""
# Session telemetry only; never supplied to route learning or World State.
const ATTEMPT_HISTORY_LIMIT := 32
var recent_attempts: Array = []
var attempt_started_ms := 0
var attempt_started_unix := 0.0
var attempt_start := Vector2(INF,INF)
var attempt_current := Vector2(INF,INF)
var attempt_initial_m := -1.0
var attempt_counter_start: Dictionary = {}
var monotonic_clock: Callable = func() -> int: return Time.get_ticks_msec()
var wall_clock: Callable = func() -> float: return Time.get_unix_time_from_system()


func _init(value: RefCounted = null) -> void:
    memory = value

func begin(value: String, target: Vector2, world: String, start: Vector2 = Vector2(INF,INF)) -> bool:
    if identity==value and world_id==world and goal.distance_to(target)<0.05:
        return false
    var interrupted := not closed
    if interrupted:
        abort("objetivo mudou", "world_changed" if world_id!=world else "goal_changed")
    identity = value
    world_id = world
    goal = target
    steps.clear()
    distance_m = 0.0
    pending_m = 0.0
    closed = false
    valid = true
    motion_state = "walking"
    last_reason = ""
    last_serial = 0
    attempt_started_ms = int(monotonic_clock.call())
    attempt_started_unix = float(wall_clock.call())
    attempt_start = start
    attempt_current = start
    attempt_initial_m = start.distance_to(goal) if start.is_finite() else -1.0
    attempt_counter_start = {"blocked":blocked_attempts,"steps":completed_steps,"ram":causal_ram_steps,"memoria":causal_memoria_steps}
    _publish_attempt("started",_attempt_snapshot())
    save_status(true)
    return interrupted

func movement(start: Vector3, end: Vector3) -> void:
    if closed:return
    var travelled := Vector2(start.x,start.z).distance_to(Vector2(end.x,end.z))
    if not attempt_start.is_finite():
        attempt_start = Vector2(start.x,start.z)
        attempt_initial_m = attempt_start.distance_to(goal)
    attempt_current = Vector2(end.x,end.z)
    distance_m += travelled
    pending_m += travelled
    save_status()

func observe_completed(action: Dictionary) -> void:
    if closed or str(action.get("route_goal_id",""))!=identity or str(action.get("context_start",{}).get("world_id",""))!=world_id:
        return
    var serial := int(action.get("decision_serial",0))
    if serial>0 and serial<=last_serial:return
    if serial>0:last_serial = serial
    var outcome := str(action.get("outcome",""))
    if outcome=="no_passage_sensed":return
    if outcome=="blocked":
        blocked_attempts += 1
        valid = false
        return
    if not outcome in ["step_reached","goal_reached"]:
        valid = false
        return
    completed_steps += 1
    var p: Dictionary = action.get("perception",{})
    var selected: Array = action["selected"]
    var point := Vector2(float(selected[0]),float(selected[1]))
    var baseline: Array = p.get("without_working_memory",[])
    if action.get("working_memory_changed_choice",false) and baseline.size()==2 and point.distance_to(Vector2(float(baseline[0]),float(baseline[1])))>0.05:
        causal_ram_steps += 1
    baseline = p.get("without_memoria",[])
    if action.get("decision_source","")=="memoria.ia" and baseline.size()==2 and point.distance_to(Vector2(float(baseline[0]),float(baseline[1])))>0.05:
        causal_memoria_steps += 1
    steps.append({"address":memory.address(action["goal"],action["start"]),"to":selected.duplicate(),"distance_m":pending_m})
    pending_m = 0.0
    if steps.size()>LIMIT:valid = false
    if steps.size()>LIMIT:steps.pop_front()
    if outcome=="goal_reached" and float(action.get("remaining_goal_m",INF))<0.1:
        _finish_attempt("arrived")
        closed = true
        motion_state = "idle"
        arrivals += 1
        last_result = "chegou: %.1f m" % distance_m
        if valid and memory!=null and memory.enabled and memory.world_id==world_id:
            memory.observe_journey(steps)
        save_status(true)
        print("NOV_JOURNEY_COMPLETE goal=%s distance_m=%.3f quality_eligible=%s" % [identity,distance_m,str(valid)])

func status() -> Dictionary:
    return {"recoveries":recoveries,"arrivals":arrivals,"interruptions":interruptions,"blocked_attempts":blocked_attempts,
        "completed_steps":completed_steps,"causal_ram_steps":causal_ram_steps,"causal_memoria_steps":causal_memoria_steps,
        "distance_m":distance_m,"result":last_result,"active":not closed,"motion_state":motion_state,"last_reason":last_reason,
        "patterns":pattern_status.call() if pattern_status.is_valid() else {},
        "active_attempt":_attempt_snapshot() if not closed else {},"recent_attempts":recent_attempts.duplicate(true)}

func abort(reason: String, termination: String = "interrupted") -> void:
    if closed:return
    _finish_attempt(termination)
    closed = true
    valid = false
    motion_state = "idle"
    last_reason = ""
    interruptions += 1
    last_result = reason+"; caminhada interrompida"
    save_status(true)
    steps.clear()
    pending_m = 0.0

func save_status(force: bool = false) -> void:
    if OS.has_feature("web") or OS.get_cmdline_user_args().has("--offline-tour"):return
    var now := Time.get_ticks_msec()
    if not force and now-saved_at<2000:return
    saved_at = now
    var value := status()
    value["schema"] = "live-infinita-nov-learning-status/v1"
    value["world_id"] = world_id
    value["observed_at_unix"] = Time.get_unix_time_from_system()
    var path := "user://nov-learning-status-008df.json"
    var file := FileAccess.open(path+".tmp",FileAccess.WRITE)
    if file==null:return
    file.store_string(JSON.stringify(value))
    file.close()
    DirAccess.rename_absolute(path+".tmp",path)

func _attempt_snapshot() -> Dictionary:
    var now := int(monotonic_clock.call())
    return {"schema":"live-infinita-nov-journey-attempt/v1","world_id":world_id,"goal_id":identity,
        "goal":[goal.x,goal.y],"started_at_unix":attempt_started_unix,"started_monotonic_ms":attempt_started_ms,
        "duration_monotonic_ms":maxi(0,now-attempt_started_ms),"distance_m":distance_m,
        "start":[attempt_start.x,attempt_start.y] if attempt_start.is_finite() else null,
        "current":[attempt_current.x,attempt_current.y] if attempt_current.is_finite() else null,
        "initial_remaining_m":attempt_initial_m if attempt_initial_m>=0 else null,
        "remaining_m":attempt_current.distance_to(goal) if attempt_current.is_finite() else null,
        "blocked_attempts":blocked_attempts-int(attempt_counter_start.get("blocked",blocked_attempts)),
        "completed_steps":completed_steps-int(attempt_counter_start.get("steps",completed_steps)),
        "causal_ram_steps":causal_ram_steps-int(attempt_counter_start.get("ram",causal_ram_steps)),
        "causal_memoria_steps":causal_memoria_steps-int(attempt_counter_start.get("memoria",causal_memoria_steps)),
        "quality_eligible":valid,"world_write_authority":false,"learning_evidence":false}

func _finish_attempt(reason: String) -> void:
    var row := _attempt_snapshot()
    row["termination"] = reason
    row["ended_at_unix"] = float(wall_clock.call())
    row["ended_monotonic_ms"] = int(monotonic_clock.call())
    row["quality_eligible"] = valid and reason=="arrived"
    recent_attempts.append(row)
    if recent_attempts.size()>ATTEMPT_HISTORY_LIMIT:recent_attempts.pop_front()
    _publish_attempt("ended",row)
    attempt_finished.emit(row.duplicate(true))

func _publish_attempt(event: String, row: Dictionary) -> void:
    if OS.has_feature("web") or OS.get_cmdline_user_args().has("--offline-tour"):return
    var value := row.duplicate(true)
    value["event"] = event
    print("NOV_JOURNEY_ATTEMPT "+JSON.stringify(value))
