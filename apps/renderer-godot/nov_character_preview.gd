extends Node3D

# An opt-in 3D identity check. The production portrait scene is not modified.
const NatureCatalog = preload("res://nature_asset_catalog.gd")

func _ready() -> void:
    _stage()
    _forest()
    var nov: Node = get_node("NovVisual")
    nov.call("apply_visual_intent", "idle")
    var status: Dictionary = nov.call("visual_status")
    var label := Label.new()
    label.position = Vector2(18, 24)
    label.text = (
        "NOV  /  CHARACTER PREVIEW\n" +
        ("Quaternius body loaded" if status["body_loaded"] else "Body ZIP not imported: placeholder") +
        "\nAnimation retarget: " +
        ("verified" if status["retarget_verified"] else "not yet verified") +
        "\nNo live, cognition or World State mutation."
    )
    label.add_theme_color_override("font_color", Color.WHITE)
    label.add_theme_color_override("font_shadow_color", Color.BLACK)
    label.add_theme_constant_override("shadow_offset_x", 1)
    label.add_theme_constant_override("shadow_offset_y", 1)
    var layer := CanvasLayer.new()
    add_child(layer)
    layer.add_child(label)

func _stage() -> void:
    var floor := MeshInstance3D.new()
    var mesh := PlaneMesh.new()
    mesh.size = Vector2(18, 18)
    floor.mesh = mesh
    floor.position.y = -0.03
    var mat := StandardMaterial3D.new()
    mat.albedo_color = Color(0.23, 0.34, 0.25)
    floor.material_override = mat
    add_child(floor)
    var sun := DirectionalLight3D.new()
    sun.rotation_degrees = Vector3(-50, 25, 0)
    sun.light_energy = 1.35
    add_child(sun)
    var environment_node := WorldEnvironment.new()
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.45, 0.62, 0.71)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.84, 0.90, 0.85)
    environment_node.environment = environment
    add_child(environment_node)
    var camera := Camera3D.new()
    camera.projection = Camera3D.PROJECTION_PERSPECTIVE
    camera.fov = 55
    camera.position = Vector3(4.8, 3.2, 7.6)
    add_child(camera)
    camera.look_at(Vector3(0, 1.0, 0), Vector3.UP)
    camera.current = true

func _forest() -> void:
    var catalog = NatureCatalog.new()
    var entry: Dictionary = catalog.pick("tree")
    var path := str(entry.get("path", ""))
    if path.is_empty() or not ResourceLoader.exists(path):
        return
    var res: Resource = load(path)
    if not res is PackedScene:
        return
    var tree: PackedScene = res as PackedScene
    for location in [Vector3(-3.8, 0, -2.0), Vector3(3.6, 0, -2.7)]:
        var node: Node = tree.instantiate()
        if node is Node3D:
            var object: Node3D = node as Node3D
            object.position = location
            add_child(object)
        else:
            node.queue_free()
