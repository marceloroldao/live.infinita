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
    var journey = load("res://nov_navigation_journey.gd").new(memory)
    journey.begin("a",Vector2(3,0),"fixture")
    journey.movement(Vector3.ZERO,Vector3(0,0,1))
    journey.observe_completed({"route_goal_id":"a","context_start":{"world_id":"fixture"},"goal":[3,0],"start":[0,0],
        "selected":[0,1],"outcome":"step_reached","perception":{}})
    journey.movement(Vector3(0,0,1),Vector3(3,0,0))
    journey.observe_completed({"route_goal_id":"a","context_start":{"world_id":"fixture"},"goal":[3,0],"start":[0,1],
        "selected":[3,0],"outcome":"goal_reached","remaining_goal_m":0.0,"perception":{}})
    check(journey.arrivals==1 and memory.quality_journeys==1,"Only a complete physical goal should learn its route cost")
    var q: Dictionary = memory.observed_quality("3,0|0,0",Vector2(0,1))
    check(absf(float(q.get("remaining_cost_m",0.0))-(1+sqrt(10.0)))<0.001,"Remaining cost must include later physical movement")
    check(not journey.begin("a",Vector2(3,0),"fixture") and journey.closed,"A completed goal must not be replayed every frame")
    journey.begin("b",Vector2(4,0),"fixture")
    journey.movement(Vector3.ZERO,Vector3(1,0,0))
    check(journey.begin("c",Vector2(5,0),"fixture"),"New objective must interrupt the unfinished walk")
    check(journey.interruptions==1 and memory.quality_journeys==1,"An interrupted walk cannot invent successful costs")
    journey.observe_completed({"route_goal_id":"b","context_start":{"world_id":"fixture"},"goal":[4,0],"start":[0,0],
        "selected":[4,0],"outcome":"goal_reached","remaining_goal_m":0.0,"perception":{}})
    check(journey.arrivals==1,"An action from an older goal must be ignored")
    journey.movement(Vector3.ZERO,Vector3(5,0,0))
    journey.observe_completed({"route_goal_id":"c","context_start":{"world_id":"fixture"},"goal":[5,0],"start":[0,0],
        "selected":[5,0],"outcome":"blocked","perception":{}})
    journey.observe_completed({"route_goal_id":"c","context_start":{"world_id":"fixture"},"goal":[5,0],"start":[0,0],
        "selected":[5,0],"outcome":"goal_reached","remaining_goal_m":0.0,"perception":{}})
    check(memory.quality_journeys==1 and journey.blocked_attempts==1,"A collision-tainted arrival cannot be successful quality evidence")

    memory.observe_journey([{"address":"3,0|0,0","to":[1,0],"distance_m":1.0},
        {"address":"3,0|1,0","to":[3,0],"distance_m":2.0}])
    var experience = load("res://nov_navigation_experience.gd").new("")
    experience.working_memory = memory
    check(experience._quality_bonus("3,0|0,0",Vector2(0,1),1.5)<1.5,"Worse observed sequences must lose their bonus")
    check(experience._quality_bonus("3,0|0,0",Vector2(1,0),1.5)==1.5,"Best observed sequence must keep its bonus")
    var remembered := {"kind":"successful_route_step","key":"3,0|0,0","to":[0,1],
        "observation_id":"structural-event:"+"a".repeat(40),"route_quality":memory.observed_quality("3,0|0,0",Vector2(0,1))}
    memory.enabled = false
    experience.apply_recall({"entries":[remembered]})
    check(experience._quality_bonus("3,0|0,0",Vector2(0,1),2.0)<2.0,"Recovered quality must affect recall after RAM is disabled")

    var hud = load("res://world_map_hud.gd").new()
    root.add_child(hud)
    await process_frame
    hud.update_learning(experience,journey)
    check(hud._learning.visible and "Interrompidas: 1" in hud._learning.text,"Live panel must show actual interruption counters")
    check("RAM" in hud._learning.text and "Memoria.ia" in hud._learning.text,"Panel must distinguish temporary and persistent evidence")
    check(not hud._toggle.visible,"Live exploration control must remain hidden")
    hud.queue_free()
    await process_frame
    print("Live learning smoke: ",failures," failures")
    quit(1 if failures else 0)
