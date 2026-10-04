extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func turn_after(seconds: float, fps: int) -> Vector3:
    var rig = load("res://nov_camera_stabilizer.gd").new()
    var forward := Vector3.FORWARD
    var dt := 1.0 / fps
    for i in range(int(seconds * fps)):
        var previous := forward
        forward = rig.observe_motion(Vector3.ZERO, Vector3.RIGHT * dt, dt, forward)
        check(previous.angle_to(forward) <= PI / 4.0 * dt + 0.0001, "Heading must respect turn-rate cap")
    return forward
func run() -> void:
    var rig = load("res://nov_camera_stabilizer.gd").new()
    var forward := Vector3.FORWARD
    for i in range(120):
        var side := 1.0 if (i / 4) % 2 == 0 else -1.0
        forward = rig.observe_motion(Vector3.ZERO, Vector3(side,0,0) * 0.02, 1.0/60.0, forward)
    check(forward.angle_to(Vector3.FORWARD) < 0.01, "Brief alternating escape probes must not spin camera")
    var at_30 := turn_after(2.0,30)
    var at_120 := turn_after(2.0,120)
    check(at_30.angle_to(at_120) < 0.04, "Camera heading must be independent of FPS")
    check(at_30.angle_to(Vector3.RIGHT) < 0.25, "Sustained movement must eventually turn camera")
    rig.follow(Vector3.ZERO,Vector3.FORWARD*10,0.0,true)
    rig.follow(Vector3(10,4,0),Vector3(10,5,-10),0.1)
    check(rig.position.x > 0.0 and rig.position.x < 10.0,"Translation must be damped")
    check(rig.position.y > 0.0 and rig.position.y < 2.0,"Vertical following must suppress height jolts")

    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false)
    await process_frame
    var feed = stage.get_node("LiveFeed")
    feed.enabled = false
    feed.set_process(false)
    stage._position = Vector3(-160,stage._height(-160,-32),-32)
    stage._follow_camera(true,0.0,true)
    var camera_before: Vector3 = stage._camera.position
    stage._position.x += 1.0
    stage._follow_camera(false,1.0/60.0)
    check(stage._camera.position.distance_to(camera_before) < 0.5,"Small character step must not snap camera")
    check(stage._camera.position.y >= stage._height(stage._camera.position.x,stage._camera.position.z)+1.85,"Smoothed camera must remain above ground")
    check(absf(stage._camera.global_transform.basis.x.y) < 0.0001,"Horizon must remain level")

    # A smoothed eye must still be shortened by actual obstacle collision.
    var pivot: Vector3 = stage._position + Vector3(0,1.35,0)
    var wall := StaticBody3D.new()
    wall.position = pivot.lerp(stage._camera.position,0.5)
    var shape := BoxShape3D.new()
    shape.size = Vector3(6,6,0.25)
    var collision := CollisionShape3D.new()
    collision.shape = shape
    wall.add_child(collision)
    stage.add_child(wall)
    await physics_frame
    stage._follow_camera(false,1.0/60.0)
    check(stage._camera.position.distance_to(pivot) < camera_before.distance_to(pivot)*0.75,"Camera safety must constrain the smoothed pose before wall")

    # Feed packets should not independently advance the camera between frames.
    stage._live_authoritative = true
    stage._local_explore_enabled = false
    var before_packet: Vector3 = stage._camera.position
    stage._on_world_slice({"x":640.0,"y":360.0},"clearing",[],[],[],42,{})
    check(stage._camera.position.distance_to(before_packet) < 0.0001,"Regular observer updates must not re-snap camera")
    stage.queue_free()
    await process_frame
    print("Camera stabilization smoke: ",failures," failures")
    quit(1 if failures else 0)
