extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func environment(state_id: String, zone: String, vegetation: float, trees: float, rock: float, snow: float) -> Dictionary:
    return {
        "state_id": state_id,
        "regions": [{
            "region_id": "test_region",
            "ecological_zone": zone,
            "vegetation_density": vegetation,
            "tree_suitability": trees,
            "rock_exposure": rock,
            "snow_cover": snow,
        }],
    }

func run() -> void:
    var scene = load("res://world_map_preview.tscn")
    check(scene != null, "Preview scene must load")
    if scene == null:
        quit(1)
        return

    var stage = scene.instantiate()
    root.add_child(stage)
    await process_frame
    await process_frame

    stage._live_region_id = "test_region"
    stage._perceptual_vegetation.update_environment(
        environment("forest-env", "forest", 0.82, 0.80, 0.05, 0.0)
    )
    var forest_factors: Vector2 = stage._perceptual_vegetation.vegetation_factors("test_region")
    check(forest_factors.x > 0.70, "Forest must allow dense local trees")
    check(forest_factors.y > 0.85, "Forest must allow dense undergrowth")

    stage._perceptual_vegetation.update_environment(
        environment("alpine-env", "alpine_rock", 0.10, 0.10, 0.72, 0.30)
    )
    var alpine_factors: Vector2 = stage._perceptual_vegetation.vegetation_factors("test_region")
    check(alpine_factors.x == 0.0, "Alpine rock must suppress local trees")
    check(alpine_factors.y < 0.12, "Alpine rock must keep undergrowth sparse")

    stage._perceptual_vegetation.update_environment(
        environment("forest-env-2", "forest", 0.82, 0.80, 0.05, 0.0)
    )
    stage._live_region_id = "test_region"
    stage._perceptual_vegetation.rebuild(
        stage._position, stage._camera_forward, "test_region", true
    )
    check(
        stage._perceptual_vegetation.tree_visible_count() > 40,
        "Dense forest must materialize many local trees"
    )
    check(
        stage._perceptual_vegetation.undergrowth_visible_count() >= 200,
        "Dense forest must materialize dense local undergrowth within budget"
    )
    check(
        stage._perceptual_vegetation.undergrowth_visible_count() <= 220,
        "Local undergrowth must respect the bounded instance budget"
    )

    var camera: Camera3D = stage._camera
    var horizontal := Vector2(
        camera.position.x - stage._position.x,
        camera.position.z - stage._position.z
    ).length()
    check(absf(horizontal - 6.4) < 0.25, "Camera must stay near NOV")
    check(absf(camera.fov - 64.0) < 0.01, "Camera FOV must be 64 degrees")

    stage.queue_free()
    await process_frame
    print("Perceptual vegetation smoke: ", failures, " failures")
    quit(1 if failures else 0)
