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

    var near_height: float = stage._distant_relief.height_for(10.0, 100.0, 0.0)
    check(absf(near_height - 10.0) < 0.0001, "Near terrain must not be exaggerated")

    var transition_height: float = stage._distant_relief.height_for(10.0, 270.0, 0.0)
    check(transition_height > 10.0, "Mid-distance terrain must begin smooth exaggeration")
    check(transition_height < 15.5, "Mid-distance relief must remain below full scale")

    var far_height: float = stage._distant_relief.height_for(10.0, 400.0, 0.0)
    check(absf(far_height - 15.5) < 0.001, "Far relief must reach configured scale")

    var capped_high: float = stage._distant_relief.height_for(100.0, 400.0, 0.0)
    check(absf(capped_high - 118.0) < 0.001, "Positive visual delta must be capped")

    var capped_low: float = stage._distant_relief.height_for(-100.0, 400.0, 0.0)
    check(absf(capped_low + 118.0) < 0.001, "Negative visual delta must be capped")

    var local_x: float = stage._position.x + 64.0
    var local_z: float = stage._position.z
    var raw_local: float = stage._height(local_x, local_z)
    var visual_local: float = stage._distant_relief.visual_height(
        stage._height(local_x, local_z), local_x, local_z
    )
    check(absf(raw_local - visual_local) < 0.0001, "Horizon inside 180m must match physical terrain")

    stage.queue_free()
    await process_frame
    print("Distant relief smoke: ", failures, " failures")
    quit(1 if failures else 0)
