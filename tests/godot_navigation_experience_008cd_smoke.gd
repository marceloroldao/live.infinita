extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func wall(p: Vector2) -> bool:
    # U opens to the left. Goal is on the far side of its closed end.
    return (p.x >= 2.0 and p.x <= 3.0 and absf(p.y) <= 3.0) or (p.x >= -3.0 and p.x <= 3.0 and absf(p.y) >= 2.0 and absf(p.y) <= 3.0)
func run() -> void:
    var Experience = load("res://nov_navigation_experience.gd")
    var memory = Experience.new("")
    var p := Vector2.ZERO
    var goal := Vector2(6, 0)
    var retreated := false
    for i in range(3000):
        var q: Vector2 = memory.target(p, goal)
        var blocked := false
        for sample in range(1, 11):
            if wall(p.lerp(q, float(sample) / 10.0)):
                blocked = true
        if blocked:
            memory.blocked()
        else:
            p = q
            memory.arrived(goal)
        retreated = retreated or p.x < -3.0
        if p.distance_to(goal) < 0.1:
            break
    print("U trial final=",p," attempts=",memory.attempts)
    check(retreated, "Experience must retreat out of U")
    check(p.distance_to(goal) < 0.1, "Experience must reach goal after escaping U")
    check(memory.attempts > 0 and not memory.failures.is_empty(), "Failed attempts must become evidence")
    var second = Experience.new("")
    second.failures = memory.failures.duplicate(true)
    second.routes = memory.routes.duplicate(true)
    var repeat := Vector2.ZERO
    for i in range(3000):
        var q: Vector2 = second.target(repeat, goal)
        var blocked := false
        for sample in range(1, 11):
            blocked = blocked or wall(repeat.lerp(q, float(sample) / 10.0))
        if blocked:
            second.blocked()
        else:
            repeat = q
            second.arrived(goal)
        if repeat.distance_to(goal) < 0.1:
            break
    check(repeat.distance_to(goal) < 0.1, "Second trial must reuse successful escape")
    print("U second trial attempts=", second.attempts)
    check(second.attempts < memory.attempts, "Remembered escape must reduce collisions")
    var path := "user://navigation-test-008cd.cfg"
    var persisted = Experience.new(path)
    persisted.failures.clear()
    persisted.routes = memory.routes.duplicate(true)
    persisted.target(Vector2.ZERO, Vector2(5,0))
    persisted.blocked()
    var restored = Experience.new(path)
    check(restored.routes == persisted.routes, "Successful escape routes must persist across restart")
    var learned: Vector2 = restored.target(Vector2.ZERO, Vector2(5,0))
    check(learned.distance_to(Vector2(1,0)) > 0.1, "Restart must reuse failed passage instead of repeating it")
    DirAccess.remove_absolute(path)

    var stage := Node3D.new()
    root.add_child(stage)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z): return 0.0)
    motion._experience = Experience.new("")
    var body: CharacterBody3D = motion.create_body(stage, null)
    var obstacle := StaticBody3D.new()
    obstacle.position = Vector3(-98, 1, 0)
    var shape := BoxShape3D.new()
    shape.size = Vector3(0.1, 2, 8)
    var collision := CollisionShape3D.new()
    collision.shape = shape
    obstacle.add_child(collision)
    stage.add_child(obstacle)
    await physics_frame
    var current := Vector3(-100,0,0)
    var result: Dictionary = motion.advance(current, Vector2.RIGHT, Vector3(-96,0,0), 0.5, body, stage.get_world_3d().direct_space_state)
    check(not result.get("allowed",true), "Swept capsule must block thin wall even when endpoint is beyond it")
    check(result.get("position", current).x < -98.4, "Body must never cross wall")

    obstacle.queue_free()
    await physics_frame
    for fixture in [
        [Vector3(-97.5,1,0), Vector3(0.2,2,5)],
        [Vector3(-100.5,1,-2.5), Vector3(6.2,2,0.2)],
        [Vector3(-100.5,1,2.5), Vector3(6.2,2,0.2)]
    ]:
        var wall_body := StaticBody3D.new()
        wall_body.position = fixture[0]
        var wall_shape := BoxShape3D.new()
        wall_shape.size = fixture[1]
        var wall_collision := CollisionShape3D.new()
        wall_collision.shape = wall_shape
        wall_body.add_child(wall_collision)
        stage.add_child(wall_body)
    await physics_frame
    motion._experience = Experience.new("")
    var physical := Vector3(-100,0,0)
    var physical_goal := Vector3(-94,0,0)
    var backed_out := false
    for i in range(4000):
        var movement: Dictionary = motion.advance(physical, Vector2.ZERO, physical_goal, 0.1, body, stage.get_world_3d().direct_space_state, true, 10.0)
        physical = movement.get("position", physical)
        backed_out = backed_out or physical.x < -104.0
        if movement.get("reached",false):
            break
    check(backed_out, "Physical U requires retreat through its opening")
    check(physical.distance_to(physical_goal) < 0.1, "Physical body must escape U and reach goal")
    print("Physical U final=", physical, " attempts=", motion._experience.attempts)

    var preview = load("res://world_map_preview.tscn").instantiate()
    root.add_child(preview)
    preview.set_process(false)
    await process_frame
    var feed = preview.get_node("LiveFeed")
    feed.enabled = false
    feed.set_process(false)
    preview._local_motion._experience = Experience.new("")
    var x := -160.0
    var z := -32.0
    var y: float = preview._features.walk_height(x,z)
    preview._position = Vector3(x,y,z)
    preview._last_live_position = Vector3(x+8,y,z)
    var live_wall := StaticBody3D.new()
    live_wall.position = Vector3(x+2,y+2,z)
    var live_shape := BoxShape3D.new()
    live_shape.size = Vector3(0.15,4,100)
    var live_collision := CollisionShape3D.new()
    live_collision.shape = live_shape
    live_wall.add_child(live_collision)
    preview.add_child(live_wall)
    await physics_frame
    for i in range(30):
        preview._advance_live_walk(0.1)
    check(preview._position.x < x+1.6, "Live movement must use physics and cannot snap through wall")
    check(preview._local_motion._experience.anticipated_avoidances > 0 or preview._local_motion._experience.attempts > 0, "Live obstacle must trigger anticipation or attempted-action evidence")
    preview.queue_free()
    stage.queue_free()
    await process_frame
    print("Navigation experience smoke: ", failures, " failures")
    quit(1 if failures else 0)
