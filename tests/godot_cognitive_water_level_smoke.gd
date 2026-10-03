extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("z", 0.0)))

func deep_basin(_x: float, _z: float) -> float:
    return -8.0

func projection() -> Dictionary:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "water-level-test",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [{
            "region_id": "deep_lake",
            "center": {"x": 120.0, "z": -40.0},
            "elevation_bias_m": -10.0,
            "influence_radius_m": 120.0,
            "cognitive_mass": 0.8,
            "terrain_role": "basin",
            "lake_candidate": true,
        }],
        "transitions": [],
        "spatial_trails": [],
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
    var changed: bool = terrain.update(
        projection(),
        Callable(self, "flat"),
        Callable(self, "deep_basin"),
        {},
    )
    check(changed, "Projection must update")
    check(terrain.lake_count() == 1, "Exactly one cognitive lake must be created")

    var lake := host.get_node_or_null("CognitiveTerrainVisuals/MemoryLake_deep_lake")
    check(lake != null, "Memory lake node must exist")
    if lake != null:
        check(
            absf(lake.position.y - (-6.95)) < 0.001,
            "Lake surface must follow basin height plus 1.05m",
        )

    var fallback_host := Node3D.new()
    root.add_child(fallback_host)
    var fallback_terrain = script.new(fallback_host)
    fallback_terrain.update(projection(), Callable(self, "flat"))
    var fallback_lake := fallback_host.get_node_or_null(
        "CognitiveTerrainVisuals/MemoryLake_deep_lake"
    )
    check(fallback_lake != null, "Fallback lake must exist")
    if fallback_lake != null:
        check(
            absf(fallback_lake.position.y - (-1.55)) < 0.001,
            "Fallback must preserve historical lake level without sampler",
        )

    fallback_host.queue_free()
    host.queue_free()
    await process_frame
    print("Cognitive water level smoke: ", failures, " failures")
    quit(1 if failures else 0)
