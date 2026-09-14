extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    # Keep the render target portrait even when a desktop fits the OS window.
    root.content_scale_size = Vector2i(720, 1280)
    root.content_scale_mode = Window.CONTENT_SCALE_MODE_VIEWPORT
    var stage = load("res://main.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false)
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://../../examples/world-state.nov-live.bootstrap.json"))
    var original := JSON.stringify(fixture)
    stage._apply_world_state({"world": fixture})
    stage._update_lighting(0.1)
    var nov = stage.entity_nodes["nov"]
    var start: Vector2 = nov.position
    stage.director_focus_entity_id = "fire_01"
    stage.director_focus_until_ms = Time.get_ticks_msec() + 6500
    for i in range(120):
        stage._update_director_layout(1.0 / 60.0)
        nov._advance_human_walk(1.0 / 60.0)
    check(nov.position == start, "Camera must not make a stationary NOV walk")
    check(stage.camera_offset.length() <= stage.MAX_CAMERA_SHIFT, "Bounded camera")
    check(JSON.stringify(stage.world) == original, "Presentation must not mutate world")
    check(stage.entity_nodes.size() == fixture.entities.size(), "Only hot entities materialize")
    var tree = stage.entity_nodes["tree_01"]
    var variant: int = tree.variant
    tree.apply_entity(tree.entity_data)
    check(tree.variant == variant, "Entity appearance is deterministic")
    stage.world.environment.period = "night"
    var before: float = stage.night_amount
    stage._update_lighting(0.1)
    check(stage.night_amount > before and stage.night_amount - before < 0.01, "Light must interpolate")
    stage.narration_remaining = 0.0
    var output := "res://../../artifacts/godot"
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
    if DisplayServer.get_name() != "headless":
        for biome in ["forest", "river", "village", "field"]:
            stage.world.environment.biome = biome
            stage.world.environment.erase("transition")
            stage.night_amount = 1.0 if biome == "village" else 0.0
            stage.sky_material.set_shader_parameter("night_amount", stage.night_amount)
            stage.sky_material.set_shader_parameter("dusk_amount", 0.0)
            stage.entity_nodes["fire_01"].entity_data.properties.lit = true
            stage._update_director_layout(0.016)
            stage.queue_redraw()
            await create_timer(0.7).timeout
            await RenderingServer.frame_post_draw
            var capture := root.get_texture().get_image()
            check(capture.get_size() == Vector2i(720, 1280), "Native portrait dimensions")
            check(capture.save_png(output + "/" + biome + ".png") == OK, "Capture " + biome)
        var first := root.get_texture().get_image()
        await create_timer(1.0).timeout
        await RenderingServer.frame_post_draw
        var second := root.get_texture().get_image()
        check(first.get_data() != second.get_data(), "Idle scene must visibly animate")
    # Churn is bounded even if several hot sets disappear in a single frame.
    for i in range(80):
        var visual = load("res://entity_visual.gd").new()
        stage.add_child(visual)
        stage._retire_visual(visual)
    check(stage.retiring.size() <= stage.MAX_RETIRING, "Bounded departure tail")
    await create_timer(0.5).timeout
    for visual in stage.retiring:
        check(not is_instance_valid(visual), "Departure must finish")
    stage.queue_free()
    await process_frame
    print("Presentation smoke: ", failures, " failures")
    quit(1 if failures else 0)
