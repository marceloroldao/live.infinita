extends SceneTree
# Component workload diagnostic using synthetic completions, not physical or core evidence.
var failures := 0
var results: Dictionary = {"schema":"live-infinita-navigation-memory-workload-diagnostic/v1",
    "scope":"isolated_synthetic_component_records","production_learning_demonstrated":false}
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func make_memory():
    var memory = load("res://nov_navigation_working_memory.gd").new("")
    memory.world_id = "fixture"
    memory.enabled = true
    return memory
func completion(serial: int, goal: Vector2, start: Vector2, next: Vector2) -> Dictionary:
    return {"decision_serial":serial,"goal":[goal.x,goal.y],"start":[start.x,start.y],
        "selected":[next.x,next.y],"end":[next.x,next.y],"outcome":"step_reached",
        "context_start":{"world_id":"fixture"},"working_memory_changed_choice":false}
func course(length: int, changed_goal: bool) -> Dictionary:
    var memory = make_memory()
    var first_goal := Vector2(1000,0)
    for i in range(length):
        memory.observe_completed(completion(i+1,first_goal,Vector2(i,0),Vector2(i+1,0)),1000+i)
    var second_goal := Vector2(1001,0) if changed_goal else first_goal
    var hits := 0
    for i in range(length):
        var start := Vector2(i,0)
        var key: String = memory.address([second_goal.x,second_goal.y],[start.x,start.y])
        if not memory.lookup(key,2000+i).is_empty():hits += 1
        memory.observe_completed(completion(length+i+1,second_goal,start,Vector2(i+1,0)),2000+i)
    check(memory.entries.size()<=512 and memory.promoted.is_empty() and memory.causal_reuses==0,
        "Lookup and synthetic agreements must not manufacture causal promotion")
    return {"steps_per_pass":length,"destination_changed":changed_goal,
        "second_pass_lookup_hits":hits,"second_pass_lookup_misses":length-hits,
        "entries_after_second_pass":memory.entries.size(),"causal_reuses":memory.causal_reuses}
func run() -> void:
    results["short_same_goal"] = course(128,false)
    results["long_same_goal"] = course(800,false)
    results["short_changed_goal"] = course(128,true)
    check(results.short_same_goal.second_pass_lookup_hits==128,"A retained exact route can be reused")
    check(results.long_same_goal.second_pass_lookup_hits==0,"Sequential long-route cache thrashing reproduced")
    check(results.short_changed_goal.second_pass_lookup_hits==0,"Changed destination prevents exact-key match")
    var clear := func(_point: Vector2) -> Dictionary:return {"allowed":true,"clear_ahead":true}
    var memory = make_memory()
    memory.observe_completed(completion(1,Vector2(5,0),Vector2.ZERO,Vector2(0,1)),1000)
    var nav = load("res://nov_navigation_experience.gd").new("")
    nav.working_memory = memory
    nav.trial_error_enabled = true
    var selected: Vector2 = nav.target(Vector2.ZERO,Vector2(5,0),clear)
    results["retained_same_context"] = {"changed_choice":nav.working_memory_changed_choice,
        "source":nav.last_decision_source,"selected":[selected.x,selected.y]}
    check(nav.working_memory_changed_choice and selected.distance_to(Vector2(0,1))<0.001,
        "Current trial-error navigator can use a retained recommendation")
    var changed = load("res://nov_navigation_experience.gd").new("")
    changed.working_memory = memory
    changed.trial_error_enabled = true
    selected = changed.target(Vector2.ZERO,Vector2(6,0),clear)
    results["changed_destination"] = {"changed_choice":changed.working_memory_changed_choice,
        "source":changed.last_decision_source,"selected":[selected.x,selected.y]}
    check(not changed.working_memory_changed_choice and selected.distance_to(Vector2(1,0))<0.001,
        "No recommendation is invented for a different destination")
    var agree_memory = make_memory()
    agree_memory.observe_completed(completion(1,Vector2(5,0),Vector2.ZERO,Vector2(1,0)),1000)
    var agree = load("res://nov_navigation_experience.gd").new("")
    agree.working_memory = agree_memory
    agree.trial_error_enabled = true
    selected = agree.target(Vector2.ZERO,Vector2(5,0),clear)
    results["perception_agreement"] = {"changed_choice":agree.working_memory_changed_choice,
        "source":agree.last_decision_source}
    check(not agree.working_memory_changed_choice and agree.last_decision_source=="perception-working-memory-agreement",
        "Agreement is not a causal choice change")
    results["failures"] = failures
    print("008EC_MEMORY_WORKLOAD_RESULT "+JSON.stringify(results))
    print("Memory reuse workload smoke: ",failures," failures")
    quit(1 if failures else 0)
