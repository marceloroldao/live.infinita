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
    var root_scene = scene.instantiate()
    root.add_child(root_scene)
    await process_frame

    var center: Array = root_scene._decor_indices_for_tile(10, 10, 10, 10)
    var edge: Array = root_scene._decor_indices_for_tile(11, 10, 10, 10)
    var corner: Array = root_scene._decor_indices_for_tile(11, 11, 10, 10)

    check(center == [0, 1, 2, 3, 4, 5], "Center tile must keep full decor")
    check(edge == [0, 2, 4], "Edge tile must keep representative decor")
    check(corner == [1], "Corner tile must use one representative decor")
    check(center.size() + 4 * edge.size() + 4 * corner.size() == 22, "3x3 decor cap must be 22")
    check(root_scene.MAX_ACTIVE_DECOR == 22, "HUD cap must match LOD maximum")

    root_scene.queue_free()
    await process_frame
    print("Tile decor LOD smoke: ", failures, " failures")
    quit(1 if failures else 0)
