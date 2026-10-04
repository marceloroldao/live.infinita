extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("y", 0.0)))

func zero_height(_x: float, _z: float) -> float:
    return 0.0

func projection(
    raw_id: String,
    visual_id: String,
    raw_bias: float,
    visual_bias: float,
    raw_ridge: float,
    visual_ridge: float,
    visual_strength: float,
) -> Dictionary:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": raw_id,
        "visual_projection_id": visual_id,
        "world_id": "smoke-world",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "a",
                "center": {"x": -80.0, "y": 0.0},
                "elevation_bias_m": raw_bias,
                "influence_radius_m": 180.0,
                "cognitive_mass": 1.0,
                "terrain_role": "uplift",
                "lake_candidate": false,
            },
            {
                "region_id": "b",
                "center": {"x": 80.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 115.0,
                "cognitive_mass": 0.0,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
        ],
        "transitions": [{
            "from_region_id": "a",
            "to_region_id": "b",
            "count": 20,
            "strength": 1.0,
            "ridge_height_m": raw_ridge,
            "ridge_width_m": 90.0,
            "trail_strength": 0.8,
            "trail_candidate": true,
            "trail_width_m": 1.8,
        }],
        "spatial_trails": [],
        "visual_regions": [
            {
                "region_id": "a",
                "center": {"x": -80.0, "y": 0.0},
                "elevation_bias_m": visual_bias,
                "influence_radius_m": 118.0,
                "cognitive_mass": 0.03,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
            {
                "region_id": "b",
                "center": {"x": 80.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 115.0,
                "cognitive_mass": 0.0,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
        ],
        "visual_transitions": [{
            "from_region_id": "a",
            "to_region_id": "b",
            "count": 2,
            "strength": visual_strength,
            "ridge_height_m": visual_ridge,
            "ridge_width_m": 31.0,
            "trail_strength": 0.08,
            "trail_candidate": false,
            "trail_width_m": 0.85,
        }],
        "visual_spatial_trails": [],
    }

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var host := Node3D.new()
    root.add_child(host)
    var script = load("res://world_map_cognitive_terrain.gd")
    check(script != null, "Cognitive terrain script must load")
    if script == null:
        quit(1)
        return

    var terrain = script.new(host)
    var first: Dictionary = projection(
        "raw-1", "visual-1", 12.0, 0.65, 12.0, 1.65, 0.05
    )
    var changed: bool = terrain.update(
        first,
        Callable(self, "flat"),
        Callable(self, "zero_height"),
        {},
    )
    check(changed, "First visual projection must rebuild")
    check(terrain.projection_id() == "raw-1", "Raw projection id must be retained")
    check(terrain.visual_projection_id() == "visual-1", "Visual id must be retained")
    check(absf(float(terrain._anchors[0]["bias"]) - 0.65) < 0.001, "Renderer must use visual region bias")
    check(absf(float(terrain._ridges[0]["height"]) - 1.65) < 0.001, "Renderer must use visual ridge height")
    check(absf(float(terrain._ridges[0]["strength"]) - 0.05) < 0.001, "Renderer must use visual relation strength")

    var same_visual: Dictionary = projection(
        "raw-2", "visual-1", 18.0, 0.65, 14.0, 1.65, 0.05
    )
    changed = terrain.update(
        same_visual,
        Callable(self, "flat"),
        Callable(self, "zero_height"),
        {},
    )
    check(not changed, "Raw-only changes must not rebuild terrain")
    check(terrain.projection_id() == "raw-2", "Raw id should still advance for diagnostics")
    check(absf(float(terrain._anchors[0]["bias"]) - 0.65) < 0.001, "Visual geometry must remain unchanged")

    var next_visual: Dictionary = projection(
        "raw-2", "visual-2", 18.0, 1.30, 14.0, 2.30, 0.10
    )
    changed = terrain.update(
        next_visual,
        Callable(self, "flat"),
        Callable(self, "zero_height"),
        {},
    )
    check(changed, "Visual id change must rebuild terrain")
    check(absf(float(terrain._anchors[0]["bias"]) - 1.30) < 0.001, "Next visual step must be applied")
    check(absf(float(terrain._ridges[0]["height"]) - 2.30) < 0.001, "Next ridge step must be applied")

    host.queue_free()
    await process_frame
    print("Cognitive visual inertia smoke: ", failures, " failures")
    quit(1 if failures else 0)
