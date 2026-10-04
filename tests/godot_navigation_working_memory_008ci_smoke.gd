extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func action(serial: int, reused: bool = false) -> Dictionary:
    return {"decision_serial":serial,"goal":[5.0,0.0],"start":[0.0,0.0],"selected":[0.0,1.0],
        "end":[0.0,1.0],"outcome":"step_reached","context_start":{"world_id":"fixture"},
        "working_memory_key":"5,0|0,0","working_memory_changed_choice":reused}
func run() -> void:
    var Memory = load("res://nov_navigation_working_memory.gd")
    var path := "user://008ci-promotions-smoke.json"
    DirAccess.remove_absolute(path)
    var memory = Memory.new(path)
    memory.set_context({"world_id":"fixture","observer_entity_id":"nov"})
    memory.enabled = true
    memory.observe_completed(action(1),1000)
    check(memory.entries.size()==1 and memory.promoted.is_empty(),"A new success must remain temporary")
    check(not FileAccess.file_exists(path),"An unpromoted route must not create durable memory in offline fixture")
    for i in range(100):
        memory.lookup("5,0|0,0",1100)
    check(memory.causal_reuses==0,"Reads must never count as reuse")

    var experience = load("res://nov_navigation_experience.gd").new("")
    experience.working_memory = memory
    experience.decision_serial = 1
    var clear := func(_point: Vector2) -> Dictionary:return {"allowed":true,"clear_ahead":true}
    for i in range(3):
        experience.active = false
        var selected: Vector2 = experience.target(Vector2.ZERO,Vector2(5,0),clear)
        check(selected.distance_to(Vector2(0,1))<0.001,"RAM experience must influence the actual navigator")
        check(experience.working_memory_changed_choice,"Navigator must compare its choice against the RAM-disabled baseline")
        var result := action(experience.decision_serial,experience.working_memory_changed_choice)
        memory.observe_completed(result,1200+i*100)
        memory.observe_completed(result,1201+i*100) # Same completion twice cannot reinforce.
        check(memory.causal_reuses==i+1,"Only distinct successfully completed decisions count")
        check(memory.promoted.size()==(1 if i==2 else 0),"Promotion requires three successful causal reuses")
    var saved = JSON.parse_string(FileAccess.get_file_as_string(path))
    check(saved["entries"].size()==1 and saved["entries"][0]["decision_ids"].size()==3,"Promotion must persist evidence identities")
    var reopened = Memory.new(path)
    reopened.set_context({"world_id":"fixture","observer_entity_id":"nov"})
    check(reopened.entries.is_empty(),"Temporary RAM experiences must not survive restart")
    check(reopened.promoted.size()==1,"Pending promotions must survive restart")

    var unsafe = load("res://nov_navigation_experience.gd").new("")
    unsafe.working_memory = memory
    var blocked_probe := func(point: Vector2) -> Dictionary:return {"allowed":point.y<0.5,"clear_ahead":point.y<0.5}
    var chosen: Vector2 = unsafe.target(Vector2.ZERO,Vector2(5,0),blocked_probe)
    check(chosen.distance_to(Vector2(1,0))<0.001 and not unsafe.working_memory_changed_choice,"Unsafe remembered passages must be rejected")
    var failed := action(20,true)
    failed["outcome"]="blocked"
    memory.observe_completed(failed,2000)
    check(memory.entries.is_empty(),"A physical failure must invalidate the temporary candidate")

    for i in range(4):
        var changed := action(21+i,i>0)
        changed["selected"]=[0.0,-1.0]
        changed["end"]=[0.0,-1.0]
        memory.observe_completed(changed,2100+i*100)
    check(float(memory.promoted["5,0|0,0"]["summary"]["to"][1]) == -1.0,"A revised passage must be promotable after fresh successful reuses")
    var bounded = Memory.new("")
    bounded.world_id = "fixture"
    bounded.enabled = true
    for i in range(600):
        var record := action(i+1)
        record["goal"]=[float(i),5.0]
        bounded.observe_completed(record,3000+i)
    check(bounded.entries.size()<=512,"RAM must remain bounded")
    bounded.prune(700000)
    check(bounded.entries.is_empty(),"Unused temporary experiences must expire")
    memory.set_context({"world_id":"different","observer_entity_id":"nov"})
    check(memory.entries.is_empty() and memory.promoted.is_empty(),"Experience must not leak across worlds")
    var stage := Node3D.new()
    root.add_child(stage)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    motion._experience = load("res://nov_navigation_experience.gd").new("")
    motion._episodes = load("res://nov_navigation_episodes.gd").new("")
    motion._episodes.action_completed.connect(Callable(motion._experience.working_memory,"observe_completed"))
    var context := {"world_id":"fixture","observer_entity_id":"nov","world_sequence":1,"runtime_position":{"x":0.0,"y":0.0}}
    motion._episodes.set_context(context)
    motion._episodes.enabled = true
    motion._experience.working_memory.storage = ""
    motion._experience.working_memory.set_context(context)
    motion._experience.working_memory.enabled = true
    var body = motion.create_body(stage,null)
    await physics_frame
    for i in range(4):
        motion._experience.active = false
        motion.advance(Vector3.ZERO,Vector2.ZERO,Vector3(1,0,0),0.1,body,stage.get_world_3d().direct_space_state,true,10.0)
    check(motion._experience.working_memory.entries.size()==1,"Physical completions must populate RAM through the real recorder signal")
    check(motion._experience.working_memory.promoted.is_empty(),"Repeated motion that agrees with perception must not be promoted")
    check(motion._experience.last_decision_source=="perception-working-memory-agreement","Agreement must be distinguished from a changed choice")
    stage.queue_free()
    await process_frame
    print("Navigation working memory smoke: ",failures," failures")
    quit(1 if failures else 0)
