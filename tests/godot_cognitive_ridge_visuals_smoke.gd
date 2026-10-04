extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func flat(center: Dictionary) -> Vector2:
    return Vector2(
        float(center.get("x", 0.0)),
        float(center.get("y", 0.0))
    )

func zero_height(_x: float, _z: float) -> float:
    return 0.0

func projection() -> Dictionary:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "ridge-visual-test",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "a",
                "center": {"x": -100.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 90.0,
                "cognitive_mass": 0.8,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
            {
                "region_id": "b",
                "center": {"x": 0.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 90.0,
                "cognitive_mass": 0.9,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
            {
                "region_id": "c",
                "center": {"x": 110.0, "y": 30.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 90.0,
                "cognitive_mass": 0.7,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
        ],
        "transitions": [
            {
                "from_region_id": "a",
                "to_region_id": "b",
                "count": 40,
                "strength": 0.92,
                "ridge_height_m": 9.0,
                "ridge_width_m": 82.0,
                "trail_strength": 0.0,
                "trail_candidate": false,
                "trail_width_m": 0.7,
            },
            {
                "from_region_id": "b",
                "to_region_id": "c",
                "count": 25,
                "strength": 0.62,
                "ridge_height_m": 5.0,
                "ridge_width_m": 60.0,
                "trail_strength": 0.0,
                "trail_candidate": false,
                "trail_width_m": 0.7,
            },
            {
                "from_region_id": "c",
                "to_region_id": "a",
                "count": 2,
                "strength": 0.10,
                "ridge_height_m": 5.5,
                "ridge_width_m": 42.0,
                "trail_strength": 0.0,
                "trail_candidate": false,
                "trail_width_m": 0.7,
            },
        ],
        "spatial_trails": [],
    }

func environment() -> Dictionary:
    return {
        "schema": "live-infinita-environmental-state/v1",
        "state_id": "ridge-env",
        "policy": {
            "world_write_authority": false,
            "memory_is_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "a",
                "rock_exposure": 0.75,
                "snow_cover": 0.35,
                "vegetation_density": 0.22,
            },
            {
                "region_id": "b",
                "rock_exposure": 0.62,
                "snow_cover": 0.20,
                "vegetation_density": 0.30,
            },
            {
                "region_id": "c",
                "rock_exposure": 0.35,
                "snow_cover": 0.0,
                "vegetation_density": 0.55,
            },
        ],
    }

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var script = load("res://world_map_cognitive_terrain.gd")
    check(script != null, "Cognitive terrain script must load")
    if script == null:
        quit(1)
        return

    var host := Node3D.new()
    root.add_child(host)
    var terrain = script.new(host)
    var changed: bool = terrain.update(
        projection(),
        Callable(self, "flat"),
        Callable(self, "zero_height"),
        environment(),
    )
    check(changed, "Projection must update")
    check(
        terrain.ridge_range_count() == 2,
        "Only the two strong cognitive ridges must become visual ranges"
    )

    var batch := host.get_node_or_null(
        "CognitiveTerrainVisuals/MemoryRidgeRangeBatch"
    )
    check(batch != null, "Ridge ranges must be emitted as one batch")
    if batch != null:
        check(batch is MeshInstance3D, "Range batch must be MeshInstance3D")
        var mesh = batch.mesh
        check(mesh != null, "Range batch must contain mesh")
        if mesh != null:
            check(mesh.get_surface_count() == 1, "Range batch must stay one surface")
            var aabb: AABB = mesh.get_aabb()
            check(aabb.size.y > 10.0, "Strong range must have visible vertical relief")
            check(aabb.size.y < 35.0, "Visual range height must remain bounded")
        check(
            absf(batch.visibility_range_begin - 90.0) < 0.01,
            "Range must remain hidden in the near foreground"
        )

    host.queue_free()
    await process_frame
    print("Cognitive ridge visuals smoke: ", failures, " failures")
    quit(1 if failures else 0)
