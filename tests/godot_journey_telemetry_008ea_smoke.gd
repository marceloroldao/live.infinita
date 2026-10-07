extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var memory = load("res://nov_navigation_working_memory.gd").new("")
    memory.enabled = true
    memory.world_id = "fixture"
    var j = load("res://nov_navigation_journey.gd").new(memory)
    var ticks := [1000]
    var wall := [100.0]
    j.monotonic_clock = func() -> int: return ticks[0]
    j.wall_clock = func() -> float: return wall[0]
    j.begin("first",Vector2(3,0),"fixture",Vector2.ZERO)
    j.movement(Vector3.ZERO,Vector3(1,0,0))
    ticks[0] = 3500
    wall[0] = 5.0 # A corrected wall clock must not corrupt elapsed time.
    j.abort("preso","stuck_recovery")
    j.abort("duplicado","stuck_recovery")
    check(j.recent_attempts.size()==1 and j.interruptions==1,"Abort emits exactly one terminal record")
    var a: Dictionary = j.recent_attempts[0]
    check(a.duration_monotonic_ms==2500 and a.distance_m==1.0,"Interrupted physical distance and duration retained")
    check(a.initial_remaining_m==3.0 and a.remaining_m==2.0,"Initial and final goal distance observed")
    check(a.termination=="stuck_recovery" and not a.quality_eligible and memory.quality_journeys==0,"Recovery is not arrival or quality evidence")
    j.begin("second",Vector2(3,0),"fixture",Vector2(1,0))
    ticks[0] = 4500
    j.movement(Vector3(1,0,0),Vector3(3,0,0))
    j.observe_completed({"route_goal_id":"second","context_start":{"world_id":"fixture"},"goal":[3,0],"start":[1,0],"selected":[3,0],"outcome":"goal_reached","remaining_goal_m":0.0,"perception":{}})
    a = j.recent_attempts[-1]
    check(a.termination=="arrived" and a.duration_monotonic_ms==1000 and a.distance_m==2.0,"Arrival has independent duration and distance")
    check(j.arrivals==1 and memory.quality_journeys==1,"Existing quality learning remains intact")
    j.begin("second",Vector2(3,0),"fixture",Vector2(1,0))
    j.abort("late")
    check(j.recent_attempts.size()==2,"Completed identity is never replayed")
    j.begin("third",Vector2(8,0),"fixture",Vector2(3,0))
    j.begin("fourth",Vector2(9,0),"fixture",Vector2(3,0))
    check(j.recent_attempts[-1].goal_id=="third" and j.recent_attempts[-1].termination=="goal_changed","Goal change closes the old identity")
    j.begin("fifth",Vector2(9,0),"other",Vector2(3,0))
    check(j.recent_attempts[-1].termination=="world_changed","World change closes old world separately")
    check(j.status().active_attempt.goal_id=="fifth","Active attempt retained in heartbeat")
    for i in range(40):
        j.abort("pause","feed_unavailable")
        j.begin("bounded:"+str(i),Vector2(10,0),"other",Vector2.ZERO)
    check(j.recent_attempts.size()==32,"In-memory attempt history stays bounded")
    check(JSON.parse_string(JSON.stringify(j.status()))!=null,"Telemetry serializes without infinite vectors")
    var route = load("res://nov_route_goal.gd").new()
    route.choose(Vector3.ZERO,Vector3(100,0,0),0.1,"fixture")
    var old: String = route.identity()
    route.elapsed = 179.95
    route.choose(Vector3.ZERO,Vector3(100,0,0),0.1,"fixture")
    check(route.last_ended_id==old and route.last_ended_reason=="goal_idle_timeout","Idle expiry retains old route identity")
    old = route.identity()
    route.total_elapsed = 899.95
    route.choose(Vector3(8,0,0),Vector3(100,0,0),0.1,"fixture")
    check(route.last_ended_id==old and route.last_ended_reason=="goal_hard_timeout","Hard expiry distinct despite fresh area")
    route.choose(Vector3(8,0,0),Vector3(100,0,0),0.1,"fixture")
    check(route.last_ended_reason.is_empty(),"Expiry marker lasts only the committing frame")
    print("Journey telemetry smoke: ",failures," failures")
    quit(1 if failures else 0)
