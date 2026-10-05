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
    var circuit := [{"address":"5,0|0,0","to":[1,0],"distance_m":1.0},
        {"address":"5,0|1,0","to":[0,0],"distance_m":1.0},
        {"address":"5,0|0,0","to":[1,0],"distance_m":1.0},
        {"address":"5,0|1,0","to":[5,0],"distance_m":4.0}]
    memory.observe_journey(circuit)
    var q: Dictionary = memory.observed_quality("5,0|0,0",Vector2(1,0))
    check(q.samples==1,"A repeated step inside one journey is only one independent quality sample")
    check(q.remaining_cost_m==7.0,"The earliest departure must retain the full later circuit cost")
    memory.observe_journey([{"address":"5,0|0,0","to":[1,0],"distance_m":1.0},
        {"address":"5,0|1,0","to":[5,0],"distance_m":4.0}])
    q = memory.observed_quality("5,0|0,0",Vector2(1,0))
    check(q.samples==2 and q.remaining_cost_m==6.0,"A separate journey supplies a second observed cost")
    for i in range(40):memory.observe_journey(circuit)
    q = memory.observed_quality("5,0|0,0",Vector2(1,0))
    check(q.samples==32,"Independent journey influence must remain bounded")
    check(memory.promoted.is_empty(),"Journey costs alone cannot manufacture causal promotions")
    var legacy = load("res://nov_navigation_working_memory.gd").new("")
    legacy.enabled = true
    legacy.quality["5,0|0,0@20,0"] = {"remaining_cost_m":15.0,"reference_cost_m":15.0,"samples":32}
    legacy.observe_journey([{"address":"5,0|0,0","to":[1,0],"distance_m":5.0}])
    var restored: Dictionary = legacy.observed_quality("5,0|0,0",Vector2(1,0))
    check(restored.samples==2 and restored.remaining_cost_m==10.0,"Older visit counts must migrate as one prior cost estimate")
    check(restored.sample_unit=="completed_journey","Persisted sample units must distinguish new complete journeys")
    var journey = load("res://nov_navigation_journey.gd").new(memory)
    journey.begin("active",Vector2(5,0),"fixture")
    journey.movement(Vector3.ZERO,Vector3(2,0,0))
    var hud = load("res://world_map_hud.gd").new()
    root.add_child(hud)
    await process_frame
    hud.update_learning(load("res://nov_navigation_experience.gd").new(""),journey)
    check("Caminhando: 2.0 m" in hud._learning.text,"Live panel must show this journey's current travel")
    check(not "Lembrar não garante melhoria" in hud._learning.text,"Unrequested disclaimer must be absent")
    hud.queue_free()
    await process_frame
    print("Journey samples smoke: ",failures," failures")
    quit(1 if failures else 0)
