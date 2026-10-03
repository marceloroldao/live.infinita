extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("y", 0.0)))

func height(_x: float, _z: float) -> float:
    return 0.0

func make_projection(pid: String, ridge_height: float) -> Dictionary:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": pid,
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "a",
                "center": {"x": -80.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 48.0,
                "cognitive_mass": 0.8,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
            {
                "region_id": "b",
                "center": {"x": 80.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 48.0,
                "cognitive_mass": 0.8,
                "terrain_role": "memory_field",
                "lake_candidate": false,
            },
        ],
        "transitions": [{
            "from_region_id": "a",
            "to_region_id": "b",
            "count": 10,
            "strength": 1.0,
            "ridge_height_m": ridge_height,
            "ridge_width_m": 70.0,
            "trail_strength": 0.0,
            "trail_candidate": false,
            "trail_width_m": 0.7,
        }],
        "spatial_trails": [],
    }

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var host := Node3D.new()
    root.add_child(host)
    var script = load("res://world_map_cognitive_terrain.gd")
    check(script != null, "Cognitive terrain must load")
    if script == null:
        quit(1)
        return

    var terrain = script.new(host)
    terrain.update(
        make_projection("low", 4.5),
        Callable(self, "flat"),
        Callable(self, "height"),
        {},
    )
    var low: float = terrain.height_delta(0.0, 0.0)

    terrain.update(
        make_projection("high", 9.0),
        Callable(self, "flat"),
        Callable(self, "height"),
        {},
    )
    var high: float = terrain.height_delta(0.0, 0.0)

    check(high > low + 1.5, "Renderer must preserve stronger ridge topology")
    check(high <= 22.0, "Renderer must retain global uplift bound")

    host.queue_free()
    await process_frame
    print("Cognitive ridge topology smoke: ", failures, " failures low=", low, " high=", high)
    quit(1 if failures else 0)
