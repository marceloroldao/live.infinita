extends Node3D

# Offline 3D composition preview, never loaded by main.tscn or World State.
# Reuses only the already catalogued Quaternius Standard glTF resources.
const Catalog = preload("res://nature_asset_catalog.gd")
const TREE_ROWS := 7
const ROCK_COUNT := 10
const PLANT_COUNT := 14
const MAX_VISUALS := TREE_ROWS * 2 + ROCK_COUNT + PLANT_COUNT

var _asset_cache: Dictionary = {}
var _placed := 0
var _missing := 0


func _ready() -> void:
    _stage()
    var catalog = Catalog.new()
    _forest(catalog)
    _caption()


func _stage() -> void:
    var ground := MeshInstance3D.new()
    var plane := PlaneMesh.new()
    plane.size = Vector2(16.0, 21.0)
    ground.mesh = plane
    ground.material_override = _material(Color("#496b46"))
    add_child(ground)

    # A visible, navigational-looking visual cue, NOT a new World State road.
    var trail := MeshInstance3D.new()
    var strip := PlaneMesh.new()
    strip.size = Vector2(2.5, 20.0)
    trail.mesh = strip
    trail.position.y = 0.012
    trail.material_override = _material(Color("#8b795a"))
    add_child(trail)
    for i in range(16):
        var stone := MeshInstance3D.new()
        var rock := BoxMesh.new()
        rock.size = Vector3(0.18 + float(i % 3) * 0.04, 0.045, 0.13)
        stone.mesh = rock
        stone.position = Vector3(sin(float(i) * 14.3) * 0.95, 0.047, -8.3 + i * 1.1)
        stone.material_override = _material(Color("#ada488"))
        add_child(stone)

    var sun := DirectionalLight3D.new()
    sun.rotation_degrees = Vector3(-52.0, 28.0, 0)
    sun.light_energy = 1.35
    sun.shadow_enabled = false
    add_child(sun)
    var atmosphere := WorldEnvironment.new()
    var env := Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color("#86afbd")
    env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color = Color("#e4e8d9")
    atmosphere.environment = env
    add_child(atmosphere)
    var camera := Camera3D.new()
    camera.projection = Camera3D.PROJECTION_ORTHOGONAL
    camera.size = 19.0
    camera.position = Vector3(9.0, 13.0, 17.0)
    add_child(camera)
    camera.look_at(Vector3(0, 0.9, 0))
    camera.current = true


func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 1.0
    return material


func _forest(catalog: RefCounted) -> void:
    # Fixed spatial budget. The central path stays open. No random() calls
    # or per-frame instantiation, and no private memory or world API reads.
    for row in range(TREE_ROWS):
        var z := -7.6 + float(row) * 2.4
        for side in [-1, 1]:
            var side_f := float(side)
            var x := side_f * (2.7 + float((row * 3 + side + 2) % 4) * 0.64)
            _spawn(catalog, "tree", row * 7 + side + 8,
                Vector3(x, 0.0, z + sin(float(row * 3 + side)) * 0.42), 3.45)
    for i in range(ROCK_COUNT):
        var side := -1.0 if i % 2 == 0 else 1.0
        _spawn(catalog, "rock", i * 3 + 1,
            Vector3(side * (1.85 + float(i % 3) * 0.45), 0.0, -8.8 + float(i) * 1.87), 0.62)
    for i in range(PLANT_COUNT):
        var side := -1.0 if i % 2 == 0 else 1.0
        _spawn(catalog, "plant", i * 5 + 2,
            Vector3(side * (1.75 + float((i * 7) % 6) * 0.63), 0.0, -8.7 + float(i) * 1.25), 0.64)


func _spawn(catalog: RefCounted, kind: String, variant: int, location: Vector3, height: float) -> void:
    if _placed + _missing >= MAX_VISUALS:
        return
    var entry: Dictionary = catalog.call("pick", kind, variant)
    var path := str(entry.get("path", ""))
    if path.is_empty() or not ResourceLoader.exists(path):
        _missing += 1
        return
    if not _asset_cache.has(path):
        var loaded: Resource = load(path)
        if not loaded is PackedScene:
            _missing += 1
            return
        _asset_cache[path] = loaded
    var packed: PackedScene = _asset_cache[path]
    var raw: Node = packed.instantiate()
    if not raw is Node3D:
        raw.queue_free()
        _missing += 1
        return
    var model: Node3D = raw
    add_child(model)
    var bounds := _bounds(model)
    var extent := maxf(maxf(bounds.size.x, bounds.size.y), bounds.size.z)
    var factor := clampf(height / maxf(extent, 0.1), 0.08, 3.0)
    model.scale = Vector3.ONE * factor
    model.position = location + Vector3(0.0, -bounds.position.y * factor, 0.0)
    _placed += 1


func _bounds(root: Node3D) -> AABB:
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


func _caption() -> void:
    var layer := CanvasLayer.new()
    add_child(layer)
    var text := Label.new()
    text.position = Vector2(22, 28)
    text.text = "LIVE INFINITA / FLORESTA 3D\nQuaternius Standard: %d modelos | %d ausentes\nPreview isolado; mundo e Nov inalterados" % [_placed, _missing]
    text.add_theme_color_override("font_color", Color.WHITE)
    text.add_theme_color_override("font_shadow_color", Color.BLACK)
    text.add_theme_constant_override("shadow_offset_x", 1)
    text.add_theme_constant_override("shadow_offset_y", 1)
    layer.add_child(text)
    print("FOREST_PREVIEW_READY placed=%d missing=%d budget=%d" % [_placed, _missing, MAX_VISUALS])
