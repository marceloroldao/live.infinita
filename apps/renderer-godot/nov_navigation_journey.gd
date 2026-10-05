extends RefCounted
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

func _init(value: RefCounted = null) -> void:
    memory = value

func begin(value: String, target: Vector2, world: String) -> bool:
    if identity==value and world_id==world and goal.distance_to(target)<0.05:
        return false
    var interrupted := not closed
    if interrupted:
        interruptions += 1
        last_result = "objetivo mudou; caminhada interrompida"
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
    return interrupted

func movement(start: Vector3, end: Vector3) -> void:
    if closed:return
    var travelled := Vector2(start.x,start.z).distance_to(Vector2(end.x,end.z))
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
        "distance_m":distance_m,"result":last_result,"active":not closed,"motion_state":motion_state,"last_reason":last_reason}

func abort(reason: String) -> void:
    if closed:return
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
