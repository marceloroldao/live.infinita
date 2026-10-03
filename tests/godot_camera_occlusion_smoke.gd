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
    check(scene != null, "Preview must load")
    if scene == null:
        quit(1)
        return

    var stage = scene.instantiate()
    root.add_child(stage)
    await process_frame
    await physics_frame

    stage._camera_forward = Vector3(0.0, 0.0, -1.0)
    stage._follow_camera(false)
    var unobstructed: Vector3 = stage._camera.position
    var pivot: Vector3 = stage._position + Vector3(0.0, 1.35, 0.0)
    var distance_before := pivot.distance_to(unobstructed)

    var body := StaticBody3D.new()
    body.name = "CameraOcclusionSmoke"
    var shape := BoxShape3D.new()
    shape.size = Vector3(4.0, 5.0, 1.0)
    var collision := CollisionShape3D.new()
    collision.shape = shape
    body.add_child(collision)
    body.position = pivot.lerp(unobstructed, 0.55)
    stage.add_child(body)

    await physics_frame
    await physics_frame

    stage._follow_camera(false)
    var obstructed: Vector3 = stage._camera.position
    var distance_after := pivot.distance_to(obstructed)

    check(
        distance_after < distance_before - 0.4,
        "Occluded camera must move closer to NOV"
    )
    check(
        distance_after > 0.5,
        "Occluded camera must preserve collision margin"
    )

    var features = stage._features
    var marker_parent := Node3D.new()
    stage.add_child(marker_parent)
    features.set_landmark_markers_visible(false)
    features._landmark(
        marker_parent,
        Vector3.ZERO,
        Color.WHITE,
        "Hidden landmark",
    )
    check(
        marker_parent.get_child_count() == 0,
        "Presentation mode must not create landmark marker or label"
    )

    body.queue_free()
    marker_parent.queue_free()
    stage.queue_free()
    await process_frame
    print("Camera occlusion smoke: ", failures, " failures")
    quit(1 if failures else 0)
