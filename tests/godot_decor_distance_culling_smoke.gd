extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var preview_script = load("res://world_map_preview.gd")
    var preview = preview_script.new()

    check(is_equal_approx(preview._decor_visibility_range("tree"), 145.0), "Tree cull range")
    check(is_equal_approx(preview._decor_visibility_range("rock"), 110.0), "Rock cull range")
    check(is_equal_approx(preview._decor_visibility_range("plant"), 82.0), "Plant cull range")

    var model := Node3D.new()
    var primary := MeshInstance3D.new()
    primary.mesh = BoxMesh.new()
    model.add_child(primary)
    var nested := Node3D.new()
    model.add_child(nested)
    var secondary := MeshInstance3D.new()
    secondary.mesh = SphereMesh.new()
    nested.add_child(secondary)

    var applied: int = preview._apply_decor_culling(model, 82.0)
    check(applied == 2, "Culling must reach nested geometry")
    check(is_equal_approx(primary.visibility_range_end, 82.0), "Primary range")
    check(is_equal_approx(secondary.visibility_range_end, 82.0), "Nested range")
    check(is_equal_approx(primary.visibility_range_end_margin, 12.0), "Primary margin")
    check(
        primary.visibility_range_fade_mode == GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED,
        "Culling must avoid fade overhead",
    )

    model.free()
    preview.free()
    print("Decor distance culling smoke: ", failures, " failures")
    quit(1 if failures else 0)
