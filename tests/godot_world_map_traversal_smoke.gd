extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func set_feet(stage, feet: Vector3) -> void:
    stage._position = feet
    stage._sync_tiles()
    stage._follow_camera(true)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var scene: PackedScene = load("res://world_map_preview.tscn")
    var stage = scene.instantiate()
    root.add_child(stage)
    stage.set_process(false)
    var feed = stage.get_node_or_null("LiveFeed")
    if feed != null:
        feed.enabled = false
        feed.set_process(false)
    await process_frame
    await physics_frame
    var body = stage.get_node_or_null("LocalExplorerBody")
    check(body != null and body is CharacterBody3D, "Local explorer must be CharacterBody3D")
    if body == null:
        quit(1)
        return
    var walk := Callable(stage._features, "walk_height")
    var water := Vector3(21.0, float(walk.call(21.0, 0.0)), 0.0)
    set_feet(stage, water)
    await physics_frame
    var result: Dictionary = stage._local_motion.advance(
        water, Vector2(1, 0), stage._waypoint([9, 7]), 0.20, body,
        stage.get_world_3d().direct_space_state
    )
    check(not bool(result.get("allowed", true)), "River outside bridge must be blocked")
    check(str(result.get("reason", "")) == "river_without_bridge", "River block reason")

    var bridge := Vector3(21.0, float(walk.call(21.0, -32.0)), -32.0)
    set_feet(stage, bridge)
    await physics_frame
    result = stage._local_motion.advance(
        bridge, Vector2(1, 0), stage._waypoint([9, 7]), 0.20, body,
        stage.get_world_3d().direct_space_state
    )
    var crossed: Vector3 = result.get("position", bridge)
    check(bool(result.get("allowed", false)), "Bridge must be walkable")
    check(str(result.get("surface", "")) == "bridge", "Bridge surface classification")
    check(crossed.x > bridge.x, "Physical body must advance on bridge")
    var body_feet: Vector3 = body.position - Vector3(0, 0.9, 0)
    check(absf(body_feet.x - crossed.x) < 0.02, "Physical/logical X synchronized")
    check(absf(body_feet.z - crossed.z) < 0.02, "Physical/logical Z synchronized")
    var house := Vector3(202.5, float(walk.call(202.5, 111.0)), 111.0)
    set_feet(stage, house)
    await process_frame
    await physics_frame
    result = stage._local_motion.advance(
        house, Vector2(1, 0), stage._waypoint([12, 9]), 0.20, body,
        stage.get_world_3d().direct_space_state
    )
    check(not bool(result.get("allowed", true)), "House collider must block candidate")
    check(str(result.get("reason", "")) == "static_obstacle", "House block reason")

    stage._on_world_slice(
        {"x": 640.0, "y": 360.0}, "clearing", [], [],
        [{"id":"clearing","center":{"x":640.0,"y":360.0},"radius":150.0}],
        999
    )
    var authoritative: Vector3 = stage._position
    Input.action_press("ui_right")
    stage._process(0.20)
    Input.action_release("ui_right")
    check(stage._position.distance_to(authoritative) < 0.001, "Live authority must ignore local input")

    stage._hud._apply_mode(true, true)
    stage._hud._press_action("ui_right")
    stage._process(0.20)
    stage._hud._release_action("ui_right")
    var explored: Vector3 = stage._position
    check(explored.distance_to(authoritative) > 0.01, "Touch local mode must allow physical exploration")

    stage._on_world_slice(
        {"x": 930.0, "y": 390.0}, "shelter", [], [],
        [{"id":"shelter","center":{"x":930.0,"y":390.0},"radius":120.0}],
        1000
    )
    check(stage._position.distance_to(explored) < 0.001, "Live update must not overwrite local explorer")
    var latest_live: Vector3 = stage._live_visual.project_position({"x":930.0,"y":390.0})
    stage._hud._apply_mode(false, true)
    check(stage._position.distance_to(latest_live) < 0.001, "Return-to-Nov must restore latest authoritative pose")

    stage.queue_free()
    await process_frame
    print("World-map traversal smoke: ", failures, " failures")
    quit(1 if failures else 0)
