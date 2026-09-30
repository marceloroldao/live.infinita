extends RefCounted
# Visual-only lightweight landmarks, paths and bridge; never affects simulation.
const CELL_M := 64.0
const HALF := 512.0
const RIVER_X := 32.0
const BRIDGE_Z := -32.0
const BRIDGE_Y := 3.5
const MAX_HOUSES_PER_TILE := 1
const MAX_COLLIDERS_PER_TILE := 3
var _height_fn: Callable

func add_to_tile(tile: Node3D, cx: int, cz: int, biome: String, points: Array, height_fn: Callable, walk_fn: Callable) -> void:
    _path(tile, cx, cz, points, walk_fn)
    if biome == "river":
        _water(tile, cz)
        if cz == 7:
            _bridge(tile)
    if biome == "village":
        _village(tile, cx, cz, height_fn)
    if cx == 2 and cz == 7:
        _landmark(tile, Vector3(-352.0, height_fn.call(-352.0, -32.0), -32.0), Color("#bc914e"), "Abrigo")
    if cx == 5 and cz == 7:
        _landmark(tile, Vector3(-160.0, height_fn.call(-160.0, -32.0), -32.0), Color("#477b3a"), "Bosque antigo")
    if cx == 8 and cz == 7:
        _landmark(tile, Vector3(52.0, height_fn.call(52.0, -24.0), -24.0), Color("#59b0ca"), "Travessia do rio")
    if cx == 11 and cz == 9:
        _landmark(tile, Vector3(233.0, height_fn.call(233.0, 105.0), 105.0), Color("#ddb272"), "Aldeia")
    if cx == 12 and cz == 4:
        _landmark(tile, Vector3(288.0, height_fn.call(288.0, -224.0), -224.0), Color("#c9caaf"), "Mirante")

func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 1.0
    return material

func _box(parent: Node3D, name: String, center: Vector3, size: Vector3, color: Color) -> MeshInstance3D:
    var mesh_node := MeshInstance3D.new()
    mesh_node.name = name
    var mesh := BoxMesh.new()
    mesh.size = size
    mesh_node.mesh = mesh
    mesh_node.position = center
    mesh_node.material_override = _material(color)
    parent.add_child(mesh_node)
    return mesh_node

func _solid_box(parent: Node3D, name: String, center: Vector3, size: Vector3, color: Color) -> MeshInstance3D:
    var visual := _box(parent, name, center, size, color)
    var body := StaticBody3D.new()
    body.name = name + "_Collider"
    body.position = center
    var shape := BoxShape3D.new()
    shape.size = size
    var collision := CollisionShape3D.new()
    collision.shape = shape
    body.add_child(collision)
    parent.add_child(body)
    return visual

func _path(parent: Node3D, cx: int, cz: int, points: Array, walk_fn: Callable) -> void:
    var x0 := float(cx) * CELL_M - HALF
    var z0 := float(cz) * CELL_M - HALF
    var surface := SurfaceTool.new()
    surface.begin(Mesh.PRIMITIVE_TRIANGLES)
    var verts := 0
    for i in range(points.size() - 1):
        var a: Vector3 = points[i]
        var b: Vector3 = points[i + 1]
        var axis := Vector2(b.x - a.x, b.z - a.z)
        if axis.length_squared() < 0.01:
            continue
        var normal := Vector2(-axis.y, axis.x).normalized() * 2.5
        var steps := maxi(1, ceili(axis.length() / 2.0))
        for index in range(steps):
            var p := Vector2(a.x, a.z).lerp(Vector2(b.x, b.z), float(index) / steps)
            var q := Vector2(a.x, a.z).lerp(Vector2(b.x, b.z), float(index + 1) / steps)
            var mid := (p + q) * 0.5
            if mid.x < x0 - 2.5 or mid.x > x0 + CELL_M + 2.5 or mid.y < z0 - 2.5 or mid.y > z0 + CELL_M + 2.5:
                continue
            var v0 := Vector3(p.x + normal.x, float(walk_fn.call(p.x + normal.x, p.y + normal.y)) + 0.08, p.y + normal.y)
            var v1 := Vector3(p.x - normal.x, float(walk_fn.call(p.x - normal.x, p.y - normal.y)) + 0.08, p.y - normal.y)
            var v2 := Vector3(q.x + normal.x, float(walk_fn.call(q.x + normal.x, q.y + normal.y)) + 0.08, q.y + normal.y)
            var v3 := Vector3(q.x - normal.x, float(walk_fn.call(q.x - normal.x, q.y - normal.y)) + 0.08, q.y - normal.y)
            for vertex in [v0, v1, v2, v2, v1, v3]:
                surface.add_vertex(vertex)
            verts += 6
    if verts == 0:
        return
    surface.generate_normals()
    var instance := MeshInstance3D.new()
    instance.name = "ExplorationTrail"
    instance.mesh = surface.commit()
    var material := _material(Color("#9b825c"))
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
    instance.material_override = material
    parent.add_child(instance)

func _water(tile: Node3D, cz: int) -> void:
    var z := float(cz) * CELL_M - HALF + 32.0
    _box(tile, "RiverWater", Vector3(RIVER_X, -2.13, z), Vector3(20.0, 0.12, CELL_M), Color("#398faf"))
    # The bank is formed by the terrain itself; water is an inexpensive material.
    for shore in [-1.0, 1.0]:
        _box(tile, "RiverBank", Vector3(RIVER_X + shore * 12.2, -2.0, z),
            Vector3(1.5, 0.4, CELL_M), Color("#9c9067"))

func _bridge(tile: Node3D) -> void:
    _box(tile, "BridgeDeck", Vector3(RIVER_X, BRIDGE_Y - 0.2, BRIDGE_Z),
        Vector3(40.0, 0.45, 5.9), Color("#745035"))
    for i in range(15):
        _box(tile, "BridgePlank_%d" % i,
            Vector3(13.3 + float(i) * 2.65, BRIDGE_Y + 0.045, BRIDGE_Z),
            Vector3(2.45, 0.13, 5.6), Color("#ac8256"))
    for side in [-1.0, 1.0]:
        _solid_box(tile, "BridgeRail", Vector3(RIVER_X, BRIDGE_Y + 0.95, BRIDGE_Z + side * 3.0),
            Vector3(40.0, 0.16, 0.18), Color("#62482f"))
        for i in range(5):
            _box(tile, "BridgePost", Vector3(13.5 + float(i) * 9.2, BRIDGE_Y + 0.55, BRIDGE_Z + side * 3.0),
                Vector3(0.22, 1.35, 0.22), Color("#725337"))

func _house(tile: Node3D, cx: int, cz: int, height_fn: Callable) -> void:
    var x := float(cx) * CELL_M - HALF + (15.0 if (cx + cz) % 2 == 0 else 49.0)
    var z := float(cz) * CELL_M - HALF + (17.0 if cz % 2 == 0 else 47.0)
    var y := float(height_fn.call(x, z))
    var root := Node3D.new()
    root.name = "VillageHouse_%d_%d" % [cx, cz]
    root.position = Vector3(x, y, z)
    tile.add_child(root)
    var plaster := Color("#d6be91") if cx % 2 == 0 else Color("#bca382")
    _solid_box(root, "Walls", Vector3(0, 1.8, 0), Vector3(6.4, 3.6, 6.2), plaster)
    _box(root, "Door", Vector3(0, 1.1, 3.13), Vector3(1.4, 2.2, 0.12), Color("#60422e"))
    for side in [-1.0, 1.0]:
        var roof := _box(root, "RoofSlope", Vector3(side * 1.6, 4.08, 0),
            Vector3(3.85, 0.28, 7.1), Color("#874b38"))
        roof.rotation_degrees.z = -26.0 * side
    _box(root, "Chimney", Vector3(2.1, 5.0, -1.25), Vector3(0.7, 1.45, 0.7), Color("#756356"))

func _landmark(tile: Node3D, pos: Vector3, tint: Color, title: String) -> void:
    _box(tile, "LandmarkBase", pos + Vector3(0, 0.5, 0),
        Vector3(1.9, 1.0, 1.9), Color("#655c4c"))
    _box(tile, "LandmarkBeacon", pos + Vector3(0, 2.1, 0),
        Vector3(0.55, 2.2, 0.55), tint)
    var label := Label3D.new()
    label.text = title
    label.position = pos + Vector3(0, 3.8, 0)
    label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    label.font_size = 30
    label.pixel_size = 0.012
    tile.add_child(label)

func _init(height_fn: Callable = Callable()) -> void:
    _height_fn = height_fn

func walk_height(x: float, z: float) -> float:
    var ground: float = float(_height_fn.call(x, z))
    if absf(z - BRIDGE_Z) < 3.1 and x >= 7.0 and x <= 57.0:
        var entrance := smoothstep(7.0, 14.0, x)
        var exit_ramp := 1.0 - smoothstep(50.0, 57.0, x)
        return lerpf(ground, BRIDGE_Y, minf(entrance, exit_ramp))
    return ground

func _hut(tile: Node3D, cx: int, cz: int, height_fn: Callable) -> void:
    _house(tile, cx, cz, height_fn)

func _village(tile: Node3D, cx: int, cz: int, height_fn: Callable) -> void:
    _hut(tile, cx, cz, height_fn)
    if cx == 11 and cz == 9:
        var x := 224.0
        var z := 96.0
        var y: float = float(height_fn.call(x, z))
        _box(tile, "VillageSquare", Vector3(x, y + 0.05, z),
            Vector3(12.0, 0.12, 12.0), Color("#aa9876"))

func decorate(tile: Node3D, cx: int, cz: int, biome: String, landmarks: Array, route: Array) -> Array[String]:
    var points: Array = []
    for cell in route:
        if typeof(cell) != TYPE_ARRAY or cell.size() != 2:
            continue
        var x := (float(cell[0]) + 0.5) * CELL_M - HALF
        var z := (float(cell[1]) + 0.5) * CELL_M - HALF
        points.append(Vector3(x, float(_height_fn.call(x, z)), z))
    add_to_tile(tile, cx, cz, biome, points, _height_fn, Callable(self, "walk_height"))
    var features: Array[String] = []
    if not points.is_empty():
        features.append("trail")
    if biome == "river":
        features.append("water")
    if cx == 8 and cz == 7:
        features.append("bridge")
    if biome == "village":
        features.append("modular_hut")
    if cx == 11 and cz == 9:
        features.append("village_square")
    for landmark in landmarks:
        if typeof(landmark) != TYPE_DICTIONARY:
            continue
        if landmark.get("cell") == [cx, cz]:
            features.append("landmark_" + str(landmark.get("id", "")))
    return features
