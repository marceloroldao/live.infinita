extends RefCounted
# Low-cost visual density for CPU rendering: deterministic, unshaded MultiMeshes.
const TILE_M := 64.0
const HALF := 512.0
const MAX_PROXIES_PER_TILE := 5

var _trunk_mesh: CylinderMesh
var _crown_mesh: CylinderMesh

func _init() -> void:
    var trunk_material := StandardMaterial3D.new()
    trunk_material.albedo_color = Color("#66503a")
    trunk_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    _trunk_mesh = CylinderMesh.new()
    _trunk_mesh.top_radius = 0.22
    _trunk_mesh.bottom_radius = 0.34
    _trunk_mesh.height = 2.5
    _trunk_mesh.radial_segments = 5
    _trunk_mesh.rings = 1
    _trunk_mesh.material = trunk_material

    var crown_material := StandardMaterial3D.new()
    crown_material.albedo_color = Color("#3f7148")
    crown_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    _crown_mesh = CylinderMesh.new()
    _crown_mesh.top_radius = 0.05
    _crown_mesh.bottom_radius = 1.55
    _crown_mesh.height = 3.8
    _crown_mesh.radial_segments = 5
    _crown_mesh.rings = 1
    _crown_mesh.material = crown_material

func _count_for(biome: String) -> int:
    match biome:
        "forest": return 5
        "clearing": return 2
        "hills": return 3
        _: return 0

func _proxy_position(cx: int, cz: int, index: int, height_fn: Callable) -> Vector3:
    var phase := float(cx * 97 + cz * 151 + index * 61)
    var local_x := 6.0 + fposmod(sin(phase * 1.13) * 8191.0, 52.0)
    var local_z := 6.0 + fposmod(sin(phase * 1.71) * 5179.0, 52.0)
    var x := float(cx) * TILE_M - HALF + local_x
    var z := float(cz) * TILE_M - HALF + local_z
    return Vector3(x, float(height_fn.call(x, z)), z)

func _make_multimesh(mesh: Mesh, positions: Array[Vector3], y_offset: float) -> MultiMeshInstance3D:
    var data := MultiMesh.new()
    data.transform_format = MultiMesh.TRANSFORM_3D
    data.mesh = mesh
    data.instance_count = positions.size()
    for index in range(positions.size()):
        data.set_instance_transform(index, Transform3D(Basis.IDENTITY, positions[index] + Vector3(0, y_offset, 0)))
    var node := MultiMeshInstance3D.new()
    node.multimesh = data
    return node

func add_to_tile(tile: Node3D, cx: int, cz: int, biome: String, height_fn: Callable) -> int:
    var count := mini(_count_for(biome), MAX_PROXIES_PER_TILE)
    if count <= 0:
        return 0
    var positions: Array[Vector3] = []
    for index in range(count):
        positions.append(_proxy_position(cx, cz, index, height_fn))
    var trunks := _make_multimesh(_trunk_mesh, positions, 1.25)
    trunks.name = "ProxyTrunks"
    tile.add_child(trunks)
    var crowns := _make_multimesh(_crown_mesh, positions, 4.0)
    crowns.name = "ProxyCrowns"
    tile.add_child(crowns)
    return count
