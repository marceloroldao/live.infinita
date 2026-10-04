extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:call_deferred("run")
func snapshot() -> Dictionary:
    return {
        "schema":"live-infinita-nov-navigation-recall/v1",
        "source":"memoria.ia-local-structural-api",
        "coordinate_space":"godot-renderer-xz-metres",
        "world_id":"fixture",
        "world_write_authority":false,
        "generated_at_unix":Time.get_unix_time_from_system(),
        "entries":[{"kind":"successful_route_step","key":"5,0|0,0","to":[0.0,1.0],
            "observation_id":"structural-event:"+"a".repeat(40)}],
    }
func run() -> void:
    var Experience = load("res://nov_navigation_experience.gd")
    var clear := func(_point: Vector2) -> Dictionary: return {"allowed":true,"clear_ahead":true}
    var off = Experience.new("")
    off.apply_recall(snapshot())
    off.memoria_enabled = false
    var without: Vector2 = off.target(Vector2.ZERO,Vector2(5,0),clear)
    var on = Experience.new("")
    on.apply_recall(snapshot())
    var with_memory: Vector2 = on.target(Vector2.ZERO,Vector2(5,0),clear)
    check(without.distance_to(Vector2(1,0)) < 0.001,"Memory disabled must choose direct clear route")
    check(with_memory.distance_to(Vector2(0,1)) < 0.001,"Retrieved successful step must change choice")
    check(on.memory_decisions==1 and on.last_observation_id!="","Memory influence must be attributable to retrieved evidence")
    var obstacle := func(point: Vector2) -> Dictionary: return {"allowed":point.y<0.5,"clear_ahead":point.y<0.5}
    var unsafe = Experience.new("")
    unsafe.apply_recall(snapshot())
    var safe: Vector2 = unsafe.target(Vector2.ZERO,Vector2(5,0),obstacle)
    check(safe.distance_to(Vector2(1,0)) < 0.001,"Currently blocked remembered route must be rejected")
    check(unsafe.memory_decisions==0,"Rejected memory must not count as selected evidence")

    var duplicate_warning = Experience.new("")
    var warning := snapshot()
    warning["entries"] = [{"kind":"blocked_passage","key":"0,0>1,0","observed_count":1,
        "observation_id":"structural-event:"+"b".repeat(40)}]
    duplicate_warning.apply_recall(warning)
    var front_blocked := func(point: Vector2) -> Dictionary: return {"allowed": point.x < 0.8, "clear_ahead": point.x < 0.8}
    duplicate_warning.target(Vector2.ZERO, Vector2(5,0), front_blocked)
    check(duplicate_warning.memory_decisions==0,"A detour already forced by perception must not be attributed to memory")

    var sensor = load("res://nov_navigation_recall.gd").new()
    sensor.enabled = false
    root.add_child(sensor)
    var receiver = Experience.new("")
    sensor.snapshot_ready.connect(Callable(receiver,"apply_recall"))
    sensor._accept(JSON.stringify(snapshot()))
    check(receiver.recalled_routes.size()==1,"Snapshot must reach navigator")
    var stale := snapshot()
    stale["generated_at_unix"] = Time.get_unix_time_from_system()-200.0
    receiver.recalled_routes.clear()
    sensor._accept(JSON.stringify(stale))
    check(receiver.recalled_routes.is_empty(),"Expired snapshot cannot influence navigation")
    sensor.enabled = true
    sensor._valid_until = Time.get_unix_time_from_system()-1.0
    sensor._next_poll = Time.get_ticks_msec()+100000
    receiver.apply_recall(snapshot())
    sensor._process(0.1)
    check(receiver.recalled_routes.is_empty(),"Memory must be cleared when freshness expires")
    sensor.enabled = false

    var stage := Node3D.new()
    root.add_child(stage)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    motion._experience = Experience.new("")
    var body: CharacterBody3D = motion.create_body(stage,null)
    var wall := StaticBody3D.new()
    wall.position = Vector3(-97,1,0)
    var box := BoxShape3D.new()
    box.size = Vector3(0.25,2,6)
    var collision := CollisionShape3D.new()
    collision.shape = box
    wall.add_child(collision)
    stage.add_child(wall)
    await physics_frame
    var origin := Vector3(-100,0,0)
    var result: Dictionary = motion.advance(origin,Vector2.ZERO,Vector3(-94,0,0),0.05,body,stage.get_world_3d().direct_space_state,true,8.0)
    var resolved: Vector3 = result.get("position",origin)
    check(absf(resolved.z)>0.01,"Look-ahead must start deviating while wall is still metres away")
    check(motion._experience.anticipated_avoidances>0,"Anticipation must be counted separately")
    check(motion._experience.attempts==0 and motion._experience.failures.is_empty(),"Sensing must not fabricate attempted-action failures")
    print("Anticipation fixture memory_off=",without," memory_on=",with_memory," advance=",resolved)
    stage.queue_free()
    sensor.queue_free()
    await process_frame
    print("Navigation anticipation smoke: ",failures," failures")
    quit(1 if failures else 0)
