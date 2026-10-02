extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

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

    var nov = stage._walker.get_node_or_null("NovVisual")
    check(nov != null, "NOV visual component must replace capsule marker")
    if nov != null:
        for part_name in [
            "Torso", "Head", "PrimitiveWrap", "ArmL", "ArmR", "LegL", "LegR", "Hair"
        ]:
            check(nov.get_node_or_null(part_name) != null, "Missing low-poly NOV part: " + part_name)

    stage._follow_camera(false)
    var forward: Vector3 = stage._camera_forward.normalized()
    var expected_target: Vector3 = (
        stage._position
        + forward * 11.0
        + Vector3(0.0, 1.35, 0.0)
    )
    var expected_direction: Vector3 = (expected_target - stage._camera.position).normalized()
    var camera_direction: Vector3 = -stage._camera.global_transform.basis.z.normalized()
    check(
        camera_direction.dot(expected_direction) > 0.995,
        "Camera must look ahead into NOV's world"
    )

    var ground_delta: float = stage._camera.position.y - stage._height(
        stage._camera.position.x, stage._camera.position.z
    )
    check(ground_delta >= 1.85, "Camera must keep safe ground clearance")
    check(ground_delta < 6.0, "Camera must stay grounded, not aerial")

    stage.queue_free()
    await process_frame
    print("NOV grounded presentation smoke: ", failures, " failures")
    quit(1 if failures else 0)
