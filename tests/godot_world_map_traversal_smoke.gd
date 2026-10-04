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
    check(stage._layout.world_size_m() == 2048, "Expanded world must be 2048m")
    check(stage._layout.grid_size == 32, "Expanded world must use 32x32 sectors")
    check(stage._layout.cell(0.0) == 16, "World origin must map to center sector")
    var expanded_surface: Dictionary = stage._local_motion._traversability.surface(Vector3(700.0, 0.0, 0.0))
    check(bool(expanded_surface.get("walkable", false)), "Old 512m boundary must no longer block")
    var new_boundary: Dictionary = stage._local_motion._traversability.surface(Vector3(1023.5, 0.0, 0.0))
    check(not bool(new_boundary.get("walkable", true)), "New 2048m boundary must block")

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

    var distant_pois := [
        {"cell":[17,6], "node":"WaterfallSheet", "label":"waterfall"},
        {"cell":[20,5], "node":"WatchtowerBase", "label":"watchtower"},
        {"cell":[25,12], "node":"StandingStone_0", "label":"stone circle"},
        {"cell":[27,20], "node":"CaveSideA", "label":"cave"},
        {"cell":[22,24], "node":"MeadowMast", "label":"meadow"},
        {"cell":[5,10], "node":"RuinsWallA", "label":"ruins"},
    ]
    for poi in distant_pois:
        var poi_position: Vector3 = stage._waypoint(poi["cell"])
        set_feet(stage, poi_position)
        await process_frame
        await physics_frame
        check(stage._tiles.size() <= 9, "Distant POI must preserve 3x3 streaming cap: " + poi["label"])
        check(stage.find_child(poi["node"], true, false) != null, "Distant POI must materialize: " + poi["label"])

    var memory_center: Vector2 = stage._live_visual.project_flat({"x":640.0,"y":360.0})
    var base_memory_height: float = float(stage._height(memory_center.x, memory_center.y))
    var cognitive_fixture := {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "smoke-memory-terrain",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id":"clearing",
                "center":{"x":640.0,"y":360.0},
                "cognitive_mass":1.0,
                "elevation_bias_m":16.0,
                "influence_radius_m":120.0,
                "terrain_role":"uplift",
                "lake_candidate":false,
            },
            {
                "region_id":"meadow",
                "center":{"x":760.0,"y":560.0},
                "cognitive_mass":0.0,
                "elevation_bias_m":-8.0,
                "influence_radius_m":100.0,
                "terrain_role":"basin",
                "lake_candidate":true,
            },
        ],
        "transitions": [
            {
                "from_region_id":"clearing",
                "to_region_id":"meadow",
                "strength":0.8,
                "ridge_height_m":2.0,
                "ridge_width_m":40.0,
            }
        ],
    }
    stage._on_world_slice(
        {"x": 640.0, "y": 360.0}, "clearing", [], [],
        [{"id":"clearing","center":{"x":640.0,"y":360.0},"radius":150.0}],
        999, cognitive_fixture
    )
    check(stage._proposed_raw_height(memory_center.x, memory_center.y) > base_memory_height + 5.0,
        "Repeated memory must propose uplift")
    check(is_equal_approx(stage._height(memory_center.x, memory_center.y), base_memory_height),
        "New inference must preserve already consolidated ground")
    check(stage._cognitive_terrain.lake_count() == 1, "Memory basin must create one visual lake")
    check(stage._tiles.size() <= 9, "Cognitive terrain rebuild must preserve tile cap")
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
        1000, cognitive_fixture
    )
    check(stage._position.distance_to(explored) < 0.001, "Live update must not overwrite local explorer")
    var latest_live: Vector3 = stage._live_visual.project_position({"x":930.0,"y":390.0})
    stage._hud._apply_mode(false, true)
    check(stage._position.distance_to(latest_live) < 0.001, "Return-to-Nov must restore latest authoritative pose")

    stage.queue_free()
    await process_frame
    print("World-map traversal smoke: ", failures, " failures")
    quit(1 if failures else 0)
