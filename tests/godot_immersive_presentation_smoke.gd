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

    check(stage._hud != null, "HUD must exist")
    if stage._hud != null:
        check(not stage._hud._status.visible, "Technical status must be hidden")
        check(stage._hud._toggle.visible, "Explore control must remain visible")

    var forward: Vector3 = stage._camera_forward.normalized()
    var right := Vector3(-forward.z, 0.0, forward.x).normalized()
    var relative: Vector3 = stage._camera.position - stage._position
    var lateral: float = relative.dot(right)
    check(absf(lateral - 0.95) < 0.08, "Camera must use shoulder offset")

    var nov = stage._walker.get_node_or_null("NovVisual")
    check(nov != null, "NOV visual must exist")
    if nov != null:
        var torso = nov.get_node_or_null("Torso")
        check(torso != null, "NOV torso must exist")
        if torso != null:
            check(torso.mesh is CylinderMesh, "Fallback torso must be tapered cylinder")

    check(stage._perceptual_vegetation != null, "Perceptual vegetation module must exist")

    stage.queue_free()
    await process_frame
    print("Immersive presentation smoke: ", failures, " failures")
    quit(1 if failures else 0)
