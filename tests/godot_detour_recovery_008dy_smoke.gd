extends SceneTree
var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        push_error(message)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func flat_ground(_x: float,_z: float) -> float:return 0.0
func run() -> void:
    var watchdog = load("res://nov_stuck_recovery.gd").new()
    var destination := Vector3(100,0,0)
    # A long bank runs away from the target before its crossing becomes reachable.
    # Positions represent actual motion, never intended candidate positions.
    var interrupted := false
    for i in range(1400):
        if watchdog.observe(Vector3(0,0,float(i)*0.1),destination,0.1,true):
            interrupted = true
            break
    check(not interrupted,"A detour through new physical positions must not be reset merely for increasing goal distance")
    watchdog.reset()
    var due := false
    for i in range(1400):
        due = watchdog.observe(Vector3(sin(float(i)*0.1)*5,0,cos(float(i)*0.1)*5),destination,0.1,true)
        if due:break
    check(due,"Repeated broad circuits must still recover")
    check(watchdog.trigger_reason=="repeated_area_no_goal_progress","Circuit recovery must explain its reason")
    watchdog.reset()
    due = false
    for i in range(320):
        due = watchdog.observe(Vector3(0,0,sin(float(i))*0.2),destination,0.1,true)
        if due:break
    check(due and watchdog.trigger_reason=="confined","Small jitter must not conceal entrapment")
    watchdog.reset()
    for i in range(290):
        check(not watchdog.observe(Vector3.ZERO,destination,0.1,true),"Thirty-second attempt allowance must remain")
    check(not watchdog.observe(Vector3.ZERO,destination,0.1,false),"Idle motion clears watchdog")
    check(watchdog.observed_cells.is_empty(),"Idle reset releases observed cells")
    for i in range(290):
        check(not watchdog.observe(Vector3.ZERO,destination,0.1,true),"A new attempt gets a fresh confinement allowance")
    watchdog.reset()
    for i in range(1400):
        check(not watchdog.observe(Vector3(0,0,float(i)*0.1),destination,0.1,true),"Continuous newly observed detour remains allowed")
    check(watchdog.observed_cells.size()<=watchdog.CELL_LIMIT,"Observed cell budget remains bounded")
    check(not watchdog.observe(Vector3.ZERO,Vector3.ZERO,0.1,true),"Arrival must remain exempt")
    var holder := Node3D.new()
    root.add_child(holder)
    var wall := StaticBody3D.new()
    wall.position = Vector3(-198,1,0)
    var shape := BoxShape3D.new()
    shape.size = Vector3(1,2,400)
    var collision := CollisionShape3D.new()
    collision.shape = shape
    wall.add_child(collision)
    holder.add_child(wall)
    var motion = load("res://world_map_local_motion.gd").new(Callable(self,"flat_ground"),512.0)
    motion._experience.storage = ""
    motion._experience.working_memory.storage = ""
    motion._episodes.storage = ""
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    watchdog.reset()
    var actual := Vector3(-200,0,0)
    var across := Vector3(-190,0,0)
    var space := holder.get_world_3d().direct_space_state
    for i in range(1400):
        var step: Dictionary = motion.advance(actual,Vector2(0,1),across,0.1,body,space,false,1.0)
        actual = step["position"]
        if not step.get("allowed",false) or watchdog.observe(actual,across,0.1,true):
            check(false,"Actual capsule detouring along a wall must remain allowed without rescue")
            break
    check(actual.z>130.0 and absf(actual.x+200)<0.01,"Physical detour moves along the obstacle and preserves collision position")
    holder.queue_free()
    await process_frame
    print("Detour recovery smoke: ",failures," failures")
    quit(1 if failures else 0)
