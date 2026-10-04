extends SceneTree

var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var visual = load("res://nov_character_visual.gd").new()
    root.add_child(visual)
    await process_frame
    visual.set_process(false)
    visual.set_motion_velocity(Vector3(0, 0, 3), 1.5)
    visual._process(0.1)
    check(visual.desired_action == "walk", "Actual motion must select walking")
    check(visual.rotation.y > 0.0 and visual.rotation.y < 1.5, "Heading must turn gradually")
    var left = visual.get_node_or_null("LegL")
    var right = visual.get_node_or_null("LegR")
    if left != null and right != null:
        check(left.rotation.x * right.rotation.x < 0.0, "Legs must swing in opposition")
        check(absf(visual.get_node("ArmL").rotation.x) > 0.0, "Arms must swing")
    visual.set_motion_velocity(Vector3.ZERO, 1.5)
    var stopped_phase: float = visual._gait_phase
    for i in range(15):
        visual._process(0.1)
    check(visual.desired_action == "idle", "Stopped movement must become idle")
    check(is_equal_approx(visual._gait_phase, stopped_phase), "Stopped feet must not keep stepping")
    check(is_zero_approx(visual._walk_blend), "Walking must settle")
    visual.queue_free()
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false)
    await process_frame
    var feed = stage.get_node_or_null("LiveFeed")
    if feed != null:
        feed.enabled = false
        feed.set_process(false)
    stage._position = Vector3(-160, float(stage._features.call("walk_height", -160.0, -32.0)), -32)
    stage._last_live_position = stage._position + Vector3(2, 0, 0)
    stage._live_walk_velocity = Vector2.ZERO
    var initial: Vector3 = stage._position
    stage._advance_live_walk(0.05)
    check(stage._position.x > initial.x, "Live presentation must advance")
    check(stage._position.x < initial.x + 0.15, "Presentation must accelerate without snapping")
    for i in range(100):
        stage._advance_live_walk(0.05)
    check(absf(stage._position.x - stage._last_live_position.x) < 0.05, "Presentation must reach target without overshoot")
    check(stage._live_walk_velocity.length() < 0.05, "Arrival must settle velocity")
    stage.queue_free()
    await process_frame
    print("NOV locomotion smoke: ", failures, " failures")
    quit(1 if failures else 0)
