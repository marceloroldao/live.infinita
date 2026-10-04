extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var Experience = load("res://nov_navigation_experience.gd")
    var snapshot := {"entries":[{"kind":"successful_route_step","key":"2,0|0,0","to":[0.0,1.0],
        "observation_id":"structural-event:"+"a".repeat(40)}]}
    var clear := func(_point: Vector2) -> Dictionary: return {"allowed":true,"clear_ahead":true}
    var navigator = Experience.new("")
    navigator.apply_recall(snapshot)
    navigator.working_memory.enabled = true
    navigator.working_memory.entries["2,0|0,0"] = {"to":[0.0,1.0],"last_ms":Time.get_ticks_msec()}
    var target: Vector2 = navigator.target(Vector2.ZERO,Vector2(2,0),clear)
    check(target.distance_to(Vector2(1,0))<0.001,"Verified clear nearby goal must override obsolete RAM and persistent detours")
    check(navigator.last_decision_source=="perception" and navigator.memory_decisions==0,"Direct visible goal cannot claim causal memory use")
    check(not navigator.working_memory_changed_choice,"Ignored detour cannot count as successful RAM reuse")
    check(navigator.decision_evidence.get("goal_corridor_clear",false),"Whole-goal observation must be explicit")
    var unsafe = Experience.new("")
    unsafe.apply_recall(snapshot)
    var blocked := func(point: Vector2) -> Dictionary:
        return {"allowed":true,"clear_ahead":point.x<0.5}
    var detour: Vector2 = unsafe.target(Vector2.ZERO,Vector2(2,0),blocked)
    check(detour.distance_to(Vector2(0,1))<0.001 and not unsafe.decision_evidence.get("goal_corridor_clear",false),"Blocked whole-goal corridor must retain safe detour selection")
    check(unsafe.memory_decisions==0,"A detour already selected by perception cannot claim causal memory")
    var distant = Experience.new("")
    var far := snapshot.duplicate(true)
    far["entries"][0]["key"] = "5,0|0,0"
    distant.apply_recall(far)
    check(distant.target(Vector2.ZERO,Vector2(5,0),clear).distance_to(Vector2(0,1))<0.001,"Priority must not assume visibility beyond three metres")

    var holder := Node3D.new()
    root.add_child(holder)
    var wall := StaticBody3D.new()
    wall.position = Vector3(-97.3,1,0)
    var collision := CollisionShape3D.new()
    var box := BoxShape3D.new()
    box.size = Vector3(0.1,2,6)
    collision.shape = box
    wall.add_child(collision)
    holder.add_child(wall)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    motion._experience = Experience.new("")
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var position := Vector3(-100,0,0)
    var reached := false
    var collisions := 0
    for tick in range(50):
        var result: Dictionary = motion.advance(position,Vector2.ZERO,Vector3(-98,0,0),0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
        position = result.get("position",position)
        collisions += int(result.get("collisions",0))
        if result.get("reached",false):
            reached = true
            break
    check(reached and collisions==0,"Obstacle beyond goal must not force a detour or collision")
    check(absf(position.z)<0.001,"Physically clear corridor must stay direct")
    holder.queue_free()
    await process_frame
    print("Navigation goal quality smoke: ",failures," failures")
    quit(1 if failures else 0)
