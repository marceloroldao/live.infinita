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

    var env_node: WorldEnvironment = null
    for child in stage.get_children():
        if child is WorldEnvironment:
            env_node = child
            break
    check(env_node != null, "WorldEnvironment must exist")
    if env_node != null:
        var env := env_node.environment
        check(env != null, "Environment resource must exist")
        if env != null:
            check(env.fog_enabled, "Depth fog must be enabled")
            check(absf(env.fog_density - 0.0026) < 0.00001, "Fog density must match bounded value")
            check(absf(env.fog_aerial_perspective - 0.32) < 0.001, "Aerial perspective must match")
            check(absf(env.fog_sky_affect - 0.48) < 0.001, "Sky affect must match")
            check(not env.volumetric_fog_enabled, "Volumetric fog must stay disabled")

    stage.queue_free()
    await process_frame
    print("Atmospheric depth smoke: ", failures, " failures")
    quit(1 if failures else 0)
