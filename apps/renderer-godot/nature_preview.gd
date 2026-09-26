extends Node3D

# Optional 3D validation scene. Never loaded by the production Node2D live scene.
const Catalog = preload("res://nature_asset_catalog.gd")
const CATEGORIES := ["tree", "rock", "plant"]
const POSITIONS := [Vector3(-4.0, 0.0, 0.0), Vector3.ZERO, Vector3(4.0, 0.0, 0.0)]

func _ready() -> void:
    _build_stage()
    var catalog = Catalog.new()
    var status: Array[String] = []
    for i in range(CATEGORIES.size()):
        var kind: String = CATEGORIES[i]
        var entry: Dictionary = catalog.pick(kind)
        if entry.is_empty() or not _spawn_model(entry, POSITIONS[i]):
            _placeholder(POSITIONS[i])
            status.append("%s: not imported" % kind)
        else:
            status.append("%s: %s (%d available)" % [kind, entry.get("label", "?"), catalog.count(kind)])
    _make_overlay("LIVE.INFINITA  /  QUATERNIUS NATURE PREVIEW\n" + "\n".join(status) +
        "\nPreview only; production 2D scene remains unchanged.")

func _build_stage() -> void:
    var floor := MeshInstance3D.new()
    var plane := PlaneMesh.new()
    plane.size = Vector2(18.0, 14.0)
    floor.mesh = plane
    floor.position.y = -0.03
    var floor_material := StandardMaterial3D.new()
    floor_material.albedo_color = Color(0.26, 0.37, 0.28)
    floor.material_override = floor_material
    add_child(floor)

    var sun := DirectionalLight3D.new()
    sun.rotation_degrees = Vector3(-52.0, 28.0, 0.0)
    sun.light_energy = 1.4
    add_child(sun)

    var environment_node := WorldEnvironment.new()
    var env := Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color(0.46, 0.65, 0.75)
    env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color = Color(0.83, 0.87, 0.89)
    environment_node.environment = env
    add_child(environment_node)

    var camera := Camera3D.new()
    camera.projection = Camera3D.PROJECTION_ORTHOGONAL
    camera.size = 12.5
    camera.position = Vector3(8.0, 6.5, 12.0)
    add_child(camera)
    camera.look_at(Vector3(0, 1.0, 0), Vector3.UP)
    camera.current = true

func _spawn_model(entry: Dictionary, location: Vector3) -> bool:
    var path := str(entry.get("path", ""))
    if not ResourceLoader.exists(path):
        return false
    var resource: Resource = load(path)
    if not resource is PackedScene:
        return false
    var packed: PackedScene = resource as PackedScene
    var node: Node = packed.instantiate()
    if not node is Node3D:
        node.queue_free()
        return false
    var model: Node3D = node
    add_child(model)
    var bounds := _model_bounds(model)
    var extent := maxf(maxf(bounds.size.x, bounds.size.y), bounds.size.z)
    var factor := clampf(2.7 / maxf(extent, 0.1), 0.08, 3.0)
    model.scale = Vector3.ONE * factor
    model.position = location + Vector3(0.0, -bounds.position.y * factor, 0.0)
    return true

func _model_bounds(root: Node3D) -> AABB:
    var bounds := AABB()
    var has_point := false
    var pending: Array[Node] = [root]
    while not pending.is_empty():
        var node: Node = pending.pop_back()
        if node is MeshInstance3D:
            var mesh_node: MeshInstance3D = node
            var box := mesh_node.get_aabb()
            for x in [0.0, 1.0]:
                for y in [0.0, 1.0]:
                    for z in [0.0, 1.0]:
                        var point := root.to_local(mesh_node.to_global(
                            box.position + box.size * Vector3(x, y, z)))
                        if not has_point:
                            bounds = AABB(point, Vector3.ZERO)
                            has_point = true
                        else:
                            bounds = bounds.expand(point)
        for child in node.get_children():
            pending.append(child)
    return bounds

func _placeholder(location: Vector3) -> void:
    # Deliberately generic stand-ins: do not represent these as vendor models.
    var item := MeshInstance3D.new()
    var box := BoxMesh.new()
    box.size = Vector3(1.4, 1.4, 1.4)
    item.mesh = box
    item.position = location + Vector3(0, 0.7, 0)
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.55, 0.59, 0.60)
    item.material_override = material
    add_child(item)

func _make_overlay(message: String) -> void:
    var layer := CanvasLayer.new()
    add_child(layer)
    var label := Label.new()
    label.position = Vector2(20, 24)
    label.add_theme_color_override("font_color", Color.WHITE)
    label.add_theme_color_override("font_shadow_color", Color.BLACK)
    label.add_theme_constant_override("shadow_offset_x", 1)
    label.add_theme_constant_override("shadow_offset_y", 1)
    label.text = message
    layer.add_child(label)
