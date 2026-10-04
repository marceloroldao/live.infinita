extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var Recorder = load("res://nov_navigation_episodes.gd")
    var path := "user://008ch-episode-smoke.json"
    DirAccess.remove_absolute(path)
    var recorder = Recorder.new(path)
    recorder.enabled = true
    var context := {"world_id":"fixture", "world_sequence":10, "observer_entity_id":"nov",
        "runtime_position":{"x":350.0,"y":340.0}, "region_id":"fixture-region"}
    recorder.set_context(context)
    var evidence := {"lookahead_m":3.0,"without_memoria":[1.0,0.0],
        "candidates":[{"point":[0.0,1.0],"allowed":true,"clear_ahead":true,"reason":""}]}
    var policy := {"allowed":true,"position":Vector3(0,0,0.5),"collisions":0,"reached":false,
        "decision_source":"memoria.ia","memory_observation_id":"structural-event:"+"a".repeat(40)}
    recorder.observe(1,Vector3.ZERO,Vector3(5,0,0),Vector2(0,1),evidence,policy,100)
    check(recorder.actions.is_empty(),"Partial motion must not be reported as arrival")
    context["world_sequence"] = 11
    recorder.set_context(context)
    policy["position"] = Vector3(0,0,1)
    recorder.observe(1,Vector3(0,0,0.5),Vector3(5,0,0),Vector2(0,1),evidence,policy,200)
    check(recorder.actions.size()==1,"Completed metre must produce one result, not per-frame observations")
    var action: Dictionary = recorder.actions[0]
    check(action["outcome"]=="step_reached" and action["duration_ms"]==100,"Outcome must reflect resolved motion")
    check(action["context_start"]["world_sequence"]==10 and action["context_end"]["world_sequence"]==11,"World feed context must be recorded at both ends")
    check(action["memory_observation_id"]==policy["memory_observation_id"],"Actual causal observation ID must accompany result")
    recorder.flush(300)
    var saved = JSON.parse_string(FileAccess.get_file_as_string(path))
    check(saved["episodes"].size()==1,"Completed episode must persist atomically")
    var reloaded = Recorder.new(path)
    check(reloaded.episodes.size()==1 and reloaded.session != recorder.session,"Restart must retain old evidence and use a new session")
    var no_passage := {"allowed":true,"position":Vector3.ZERO,"reached":false,
        "decision_source":"perception-no-passage","memory_observation_id":""}
    recorder.observe(2,Vector3.ZERO,Vector3(5,0,0),Vector2.ZERO,evidence,no_passage,20000)
    recorder.observe(3,Vector3.ZERO,Vector3(5,0,0),Vector2.ZERO,evidence,no_passage,20100)
    check(recorder.actions.size()==1,"No-passage sensing must be rate limited")
    check(recorder.actions[0]["outcome"]=="no_passage_sensed","Perception cannot be fabricated as a failed physical attempt")
    recorder.flush(31000)
    # A world switch cancels unfinished work rather than attributing it to another world.
    policy["position"] = Vector3(0,0,0.5)
    recorder.observe(4,Vector3.ZERO,Vector3(5,0,0),Vector2(0,1),evidence,policy,32000)
    context["world_id"]="different"
    recorder.set_context(context)
    check(recorder.active.is_empty(),"An unfinished action must not cross world identities")
    for i in range(20):
        recorder.actions.append(action.duplicate(true))
        recorder.flush(40000+i)
    check(recorder.episodes.size()==16 and recorder.dropped>0,"Retention must remain bounded and disclose removals")

    var stage := Node3D.new()
    root.add_child(stage)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    motion._experience = load("res://nov_navigation_experience.gd").new("")
    motion._episodes = Recorder.new("")
    motion._episodes.enabled = true
    context["world_id"]="fixture"
    motion._episodes.set_context(context)
    var body = motion.create_body(stage,null)
    await physics_frame
    motion.advance(Vector3.ZERO,Vector2.ZERO,Vector3(1,0,0),0.1,body,stage.get_world_3d().direct_space_state,true,10.0)
    check(motion._episodes.actions.size()==1,"Real motion advance must reach the recorder")
    if motion._episodes.actions.size()==1:
        check(motion._episodes.actions[0]["outcome"]=="goal_reached","Physical arrival must be distinguished from intermediate steps")
    stage.queue_free()
    await process_frame
    print("Navigation episodes smoke: ",failures," failures")
    quit(1 if failures else 0)
