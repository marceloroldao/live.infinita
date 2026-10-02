extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func project_flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("z", 0.0)))

func sample_height(_x: float, _z: float) -> float:
    return 2.0

func projection() -> Dictionary:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "same-cognition",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [{
            "region_id": "peak",
            "center": {"x": 40.0, "z": 20.0},
            "elevation_bias_m": 18.0,
            "influence_radius_m": 180.0,
            "cognitive_mass": 1.0,
            "terrain_role": "uplift",
            "lake_candidate": false,
        }],
        "transitions": [],
        "spatial_trails": [],
    }

func environment(state_id: String, snow: float, rock: float, vegetation: float) -> Dictionary:
    return {
        "schema": "live-infinita-environmental-state/v1",
        "state_id": state_id,
        "policy": {
            "world_write_authority": false,
            "memory_is_authority": false,
            "selection_authority": false,
        },
        "regions": [{
            "region_id": "peak",
            "snow_cover": snow,
            "rock_exposure": rock,
            "vegetation_density": vegetation,
        }],
    }

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var terrain_script = load("res://world_map_cognitive_terrain.gd")
    var host := Node3D.new()
    root.add_child(host)
    var terrain = terrain_script.new(host)

    var cold = environment("env-cold", 0.26, 0.72, 0.06)
    var changed: bool = terrain.update(
        projection(),
        Callable(self, "project_flat"),
        Callable(self, "sample_height"),
        cold,
    )
    check(changed, "Initial cognition/environment must update")
    check(terrain.massif_count() == 1, "Cognitive uplift must create one massif")
    check(terrain.snow_cap_count() == 1, "Cold high massif must receive one snow cap")
    check(terrain.environment_state_id() == "env-cold", "Environment state id must be retained")

    var warm = environment("env-warm", 0.0, 0.22, 0.72)
    changed = terrain.update(
        projection(),
        Callable(self, "project_flat"),
        Callable(self, "sample_height"),
        warm,
    )
    check(changed, "Environmental change must rebuild same cognitive projection")
    check(terrain.massif_count() == 1, "Environmental change must preserve cognitive massif")
    check(terrain.snow_cap_count() == 0, "Warm state must remove snow cap")
    check(terrain.environment_state_id() == "env-warm", "New environment id must be retained")

    changed = terrain.update(
        projection(),
        Callable(self, "project_flat"),
        Callable(self, "sample_height"),
        warm,
    )
    check(not changed, "Identical cognition and environment must stay stable")

    host.queue_free()
    await process_frame
    print("Environmental massif smoke: ", failures, " failures")
    quit(1 if failures else 0)
