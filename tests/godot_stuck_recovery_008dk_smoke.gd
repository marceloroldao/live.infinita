extends SceneTree
class FakeAssets:
    extends RefCounted
    func rebuild(_position: Vector3,_forward: Vector3,_region: String) -> void:
        pass
class RecoveryPreview:
    extends "res://world_map_preview.gd"
    var start_wall: StaticBody3D
    var camera_reset := false
    func _ready() -> void:
        pass
    func _sync_tiles() -> void:
        if start_wall != null:return
        start_wall = StaticBody3D.new()
        start_wall.position = Vector3(-140,1,0)
        var shape := BoxShape3D.new()
        shape.size = Vector3(2,2,2)
        var collision := CollisionShape3D.new()
        collision.shape = shape
        start_wall.add_child(collision)
        add_child(start_wall)
    func _rebuild_horizon_ground() -> void:pass
    func _rebuild_distant_vegetation() -> void:pass
    func _rebuild_midground_vegetation() -> void:pass
    func _follow_camera(snap: bool = true,_delta: float = 0.016,reset: bool = false) -> void:
        camera_reset = reset
        if snap:_local_motion.snap_body(_walker,_position)
var failures := 0
var all_water := false
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func ground(x: float,z: float) -> float:
    return -5.0 if Vector2(x+100,z).length()<2.5 else 0.0
func surface(_x: float,_z: float) -> Dictionary:
    return {"walkable":not all_water,"surface":"water" if all_water else "terrain","reason":"cognitive_lake" if all_water else ""}
func run() -> void:
    var watchdog = load("res://nov_stuck_recovery.gd").new()
    var due := false
    for i in range(290):
        due = watchdog.observe(Vector3(-100,-5,0),Vector3(-90,0,0),0.1,true)
    check(not due,"Brief entrapment must allow attempts before reset")
    for i in range(20):
        due = watchdog.observe(Vector3(-100,-5,0),Vector3(-90,0,0),0.1,true)
    check(due,"Confined stationary Nov must recover after thirty seconds")
    watchdog.reset()
    for i in range(600):
        check(not watchdog.observe(Vector3(-120+float(i)*0.2,0,0),Vector3(200,0,0),0.1,true),"Normal forward progress must not trigger reset")
    watchdog.reset()
    for i in range(1200):
        if watchdog.observe(Vector3(-100+sin(float(i)*0.1)*5.0,-5,cos(float(i)*0.1)*5.0),Vector3(0,0,0),0.1,true):
            due = true
            break
        due = false
    check(due,"A wider repeated circuit without goal progress must eventually recover")
    check(not watchdog.observe(Vector3(-100,0,0),Vector3(-90,0,0),0.1,false),"Idle or disabled motion must not trigger rescue")
    check(not watchdog.observe(Vector3(-90,0,0),Vector3(-90,0,0),0.1,true),"An arrival must not count as trapped")

    var holder := Node3D.new()
    root.add_child(holder)
    var wall := StaticBody3D.new()
    wall.position = Vector3(-120,1,0)
    var shape := BoxShape3D.new()
    shape.size = Vector3(2,2,2)
    var collision := CollisionShape3D.new()
    collision.shape = shape
    wall.add_child(collision)
    holder.add_child(wall)
    var motion = load("res://world_map_local_motion.gd").new(Callable(self,"ground"),512.0,Callable(self,"surface"))
    motion._experience.storage = ""
    motion._experience.working_memory.storage = ""
    motion._episodes.storage = ""
    motion._episodes.set_context({"world_id":"pit-fixture","observer_entity_id":"nov"})
    motion._episodes.enabled = true
    motion._experience.working_memory.world_id = "pit-fixture"
    motion._experience.working_memory.enabled = true
    motion._experience.trial_error_enabled = true
    motion.route_goal_id = "pit-goal"
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var space := holder.get_world_3d().direct_space_state
    var trapped := Vector3(-100,-5,0)
    var goal := Vector3(-90,0,0)
    watchdog.reset()
    due = false
    for i in range(1000):
        var step: Dictionary = motion.advance(trapped,Vector2.ZERO,goal,0.1,body,space,true,4.0)
        trapped = step["position"]
        check(not step.get("reached",false),"Steep pit walls must not be bypassed by ordinary walking")
        check(Vector2(trapped.x+100,trapped.z).length()<2.5,"Actual local motion must remain within pit until explicit recovery")
        if watchdog.observe(trapped,goal,0.1,true):
            due = true
            break
    check(due,"Real physical pit must activate recovery")
    var before: Dictionary = motion._journey.status()
    var quality_before: int = motion._experience.working_memory.quality_journeys
    check(not motion.recover_to(trapped,Vector3(-120,0,0),body,space),"Occupied start must reject teleport before changing the journal")
    var safe: Dictionary = motion.resolve_recovery_start(Vector3(-120,0,0),space)
    check(safe.get("allowed",false),"A nearby free start with an exit must be found")
    if safe.get("allowed",false):
        check(Vector2(safe.position.x+120,safe.position.z).length()>1.0,"Recovery must not spawn inside start obstacle")
        check(motion.recover_to(trapped,safe.position,body,space),"Validated recovery should reset actual body")
        var after: Dictionary = motion._journey.status()
        check(body.position.distance_to(safe.position+Vector3(0,0.9,0))<0.001,"Actual body must land at the verified ground height")
        check(after.recoveries==1 and after.interruptions==1 and after.arrivals==before.arrivals,"Reset must be one recovery and interruption, never an arrival")
        check(after.completed_steps==before.completed_steps and absf(after.distance_m-before.distance_m)<0.001,"Teleport must not invent walked steps or distance")
        check(motion._experience.working_memory.quality_journeys==quality_before,"Failed route cannot learn successful route cost")
    all_water = true
    check(not motion.resolve_recovery_start(Vector3(-120,0,0),space).get("allowed",false),"No dry start means recovery is deferred, not forced into water")
    all_water = false
    var preview := RecoveryPreview.new()
    root.add_child(preview)
    var integrated = load("res://world_map_local_motion.gd").new(Callable(self,"ground"),512.0,Callable(self,"surface"))
    integrated._experience.storage = ""
    integrated._experience.working_memory.storage = ""
    integrated._episodes.storage = ""
    integrated._episodes.set_context({"world_id":"pit-fixture","observer_entity_id":"nov"})
    integrated._episodes.enabled = true
    integrated._experience.working_memory.world_id = "pit-fixture"
    integrated._experience.working_memory.enabled = true
    integrated.route_goal_id = "integrated-pit"
    integrated.commit_journey("integrated-pit",goal,trapped)
    preview._local_motion = integrated
    preview._walker = integrated.create_body(preview,null)
    preview._position = trapped
    preview._recovery_start = Vector3(-140,0,0)
    preview._live_walk_velocity = Vector2(4,0)
    preview._perceptual_vegetation = FakeAssets.new()
    preview._perceptual_assets = FakeAssets.new()
    await preview._attempt_stuck_recovery()
    check(not preview._recovery_pending and preview.camera_reset,"Integrated recovery must release pause and reset the camera")
    check(preview._position.distance_to(Vector3(-140,0,0))>1.0 and preview._position.distance_to(Vector3(-140,0,0))<=32.0,"Colliders loaded during recovery must prevent landing inside start obstacle")
    check(preview._live_walk_velocity.is_zero_approx() and integrated._journey.recoveries==1,"Integrated recovery must stop velocity and record one return")
    preview.queue_free()
    holder.queue_free()
    await process_frame
    print("Stuck recovery smoke: ",failures," failures")
    quit(1 if failures else 0)
