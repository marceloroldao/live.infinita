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

    var camera: Camera3D = stage._camera
    var position: Vector3 = stage._position
    check(camera != null, "Camera must exist")
    if camera != null:
        var horizontal := Vector2(
            camera.position.x - position.x,
            camera.position.z - position.z
        ).length()
        check(absf(horizontal - 9.0) < 0.2, "Camera must stay about 9 m behind NOV")
        check(camera.position.y - position.y < 12.0, "Camera must no longer be aerial")
        check(camera.position.y > stage._height(camera.position.x, camera.position.z) + 2.2,
            "Camera must clear local terrain")
        check(absf(camera.fov - 68.0) < 0.01, "Perceptual FOV must be 68 degrees")

    check(stage._live_visual._diagnostic_overlays_enabled == false,
        "Perceptual preview must hide region overlays")

    var old_forward: Vector3 = stage._camera_forward
    stage._update_camera_heading(position, position + Vector3(6.0, 0.0, 0.0))
    check(stage._camera_forward.x > old_forward.x,
        "Heading must rotate toward observed movement")

    stage.queue_free()
    await process_frame
    print("NOV perceptual camera smoke: ", failures, " failures")
    quit(1 if failures else 0)
