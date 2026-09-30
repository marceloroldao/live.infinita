extends RefCounted

const MAX_HOT_MARKERS := 96
const MAX_WARM_MARKERS := 192
const MAX_LOCAL_REGIONS := 16
const REGION_RING_SEGMENTS := 48

var _host: Node3D
var _features: RefCounted
var _map: Dictionary
var _hot_markers: MultiMeshInstance3D
var _warm_markers: MultiMeshInstance3D
var _region_root: Node3D
var _region_signature := ""
var _half_m := 512.0

func _init(host: Node3D, features: RefCounted, map_data: Dictionary) -> void:
    _host = host
    _features = features
    _map = map_data
    _half_m = float(int(_map.get("grid_size", 16))) * float(_map.get("tile_size_m", 64)) * 0.5

func build() -> void:
    _hot_markers = _marker_batch("HotEntities", Color("#ec764f"), 0.40)
    _warm_markers = _marker_batch("WarmEntities", Color("#65a9c8"), 0.24)
    _region_root = Node3D.new()
    _region_root.name = "PersistentRegions"
    _host.add_child(_region_root)

func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 1.0
    return material

func _marker_batch(name: String, color: Color, radius: float) -> MultiMeshInstance3D:
    var sphere := SphereMesh.new()
    sphere.radius = radius
    sphere.height = radius * 2.0
    sphere.radial_segments = 8
    sphere.rings = 4
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.mesh = sphere
    multimesh.instance_count = 0
    var node := MultiMeshInstance3D.new()
    node.name = name
    node.multimesh = multimesh
    node.material_override = _material(color)
    _host.add_child(node)
    return node

func _array_vec2(value: Variant, fallback: Vector2) -> Vector2:
    if typeof(value) == TYPE_ARRAY and value.size() >= 2:
        return Vector2(float(value[0]), float(value[1]))
    return fallback

func project_flat(position_data: Dictionary) -> Vector2:
    var projection = _map.get("runtime_projection", {})
    var world_point := Vector2(float(position_data.get("x", 640.0)), float(position_data.get("y", 360.0)))
    if typeof(projection) != TYPE_DICTIONARY:
        var fallback := world_point - Vector2(640.0, 360.0)
        return Vector2(
            clampf(fallback.x, -_half_m + 1.0, _half_m - 1.0),
            clampf(fallback.y, -_half_m + 1.0, _half_m - 1.0)
        )
    var wa := _array_vec2(projection.get("world_anchor_a", []), Vector2(350, 340))
    var wb := _array_vec2(projection.get("world_anchor_b", []), Vector2(930, 390))
    var ma := _array_vec2(projection.get("map_anchor_a_m", []), Vector2(-160, -32))
    var mb := _array_vec2(projection.get("map_anchor_b_m", []), Vector2(-352, -32))
    var world_axis := wb - wa
    var map_axis := mb - ma
    if world_axis.length() < 0.001 or map_axis.length() < 0.001:
        return ma
    var wu := world_axis.normalized()
    var wp := Vector2(-wu.y, wu.x)
    var mu := map_axis.normalized()
    var sign := float(projection.get("perpendicular_sign", 1.0))
    var mp := Vector2(-mu.y, mu.x) * sign
    var scale := map_axis.length() / world_axis.length()
    var offset := world_point - wa
    var mapped := ma + mu * offset.dot(wu) * scale + mp * offset.dot(wp) * scale
    mapped.x = clampf(mapped.x, -_half_m + 1.0, _half_m - 1.0)
    mapped.y = clampf(mapped.y, -_half_m + 1.0, _half_m - 1.0)
    return mapped

func project_position(position_data: Dictionary) -> Vector3:
    var mapped := project_flat(position_data)
    return Vector3(mapped.x, float(_features.call("walk_height", mapped.x, mapped.y)), mapped.y)

func _fill(batch: MultiMeshInstance3D, entities: Array, limit: int, skip_nov: bool) -> int:
    var points: Array[Vector3] = []
    for entity in entities:
        if typeof(entity) != TYPE_DICTIONARY:
            continue
        if skip_nov and str(entity.get("id", "")) == "nov":
            continue
        var position_data = entity.get("position", {})
        if typeof(position_data) != TYPE_DICTIONARY:
            continue
        points.append(project_position(position_data))
        if points.size() >= limit:
            break
    var multimesh := batch.multimesh
    multimesh.instance_count = points.size()
    for index in range(points.size()):
        multimesh.set_instance_transform(index, Transform3D(Basis.IDENTITY, points[index] + Vector3(0, 0.8, 0)))
    return points.size()

func update_markers(hot_entities: Array, warm_entities: Array) -> Dictionary:
    return {
        "hot": _fill(_hot_markers, hot_entities, MAX_HOT_MARKERS, true),
        "warm": _fill(_warm_markers, warm_entities, MAX_WARM_MARKERS, false),
    }

func clear_markers() -> void:
    if _hot_markers != null:
        _hot_markers.multimesh.instance_count = 0
    if _warm_markers != null:
        _warm_markers.multimesh.instance_count = 0

func _projection_scale() -> float:
    var projection = _map.get("runtime_projection", {})
    if typeof(projection) != TYPE_DICTIONARY:
        return 1.0
    var wa := _array_vec2(projection.get("world_anchor_a", []), Vector2(350, 340))
    var wb := _array_vec2(projection.get("world_anchor_b", []), Vector2(930, 390))
    var ma := _array_vec2(projection.get("map_anchor_a_m", []), Vector2(-160, -32))
    var mb := _array_vec2(projection.get("map_anchor_b_m", []), Vector2(-352, -32))
    var world_len := wa.distance_to(wb)
    if world_len < 0.001:
        return 1.0
    return ma.distance_to(mb) / world_len

func _region_signature_for(regions: Array, current_region_id: String) -> String:
    var parts: Array[String] = [current_region_id]
    var sorted_regions := regions.duplicate(true)
    sorted_regions.sort_custom(func(a, b): return str(a.get("id", "")) < str(b.get("id", "")))
    for region in sorted_regions.slice(0, MAX_LOCAL_REGIONS):
        if typeof(region) != TYPE_DICTIONARY:
            continue
        var center = region.get("center", {})
        parts.append("%s:%.2f:%.2f:%.2f" % [
            str(region.get("id", "")),
            float(center.get("x", 0.0)) if typeof(center) == TYPE_DICTIONARY else 0.0,
            float(center.get("y", 0.0)) if typeof(center) == TYPE_DICTIONARY else 0.0,
            float(region.get("radius", 0.0)),
        ])
    return "|".join(parts)
func _clear_region_nodes() -> void:
    if _region_root == null:
        return
    for child in _region_root.get_children():
        child.queue_free()

func _region_ring(region: Dictionary, current_region_id: String) -> void:
    var center_data = region.get("center", {})
    if typeof(center_data) != TYPE_DICTIONARY:
        return
    var radius := maxf(1.0, float(region.get("radius", 1.0)) * _projection_scale())
    var center := project_position(center_data)
    var current := str(region.get("id", "")) == current_region_id
    var color := Color("#f4d35e") if current else Color("#88b7a0")
    var mesh := ImmediateMesh.new()
    var material := _material(color)
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    mesh.surface_begin(Mesh.PRIMITIVE_LINE_STRIP, material)
    for index in range(REGION_RING_SEGMENTS + 1):
        var angle := TAU * float(index) / float(REGION_RING_SEGMENTS)
        var x := center.x + cos(angle) * radius
        var z := center.z + sin(angle) * radius
        var y := float(_features.call("walk_height", x, z)) + 0.16
        mesh.surface_add_vertex(Vector3(x, y, z))
    mesh.surface_end()
    var ring := MeshInstance3D.new()
    ring.name = "RegionRing_" + str(region.get("id", "unknown"))
    ring.mesh = mesh
    _region_root.add_child(ring)
    var label := Label3D.new()
    var metadata = region.get("metadata", {})
    var title := str(region.get("id", "region"))
    if typeof(metadata) == TYPE_DICTIONARY:
        title = str(metadata.get("label", title))
    label.text = title
    label.position = center + Vector3(0, 2.4, 0)
    label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    label.font_size = 24 if current else 18
    label.pixel_size = 0.012
    label.modulate = color
    _region_root.add_child(label)

func update_regions(regions: Array, current_region_id: String) -> int:
    var signature := _region_signature_for(regions, current_region_id)
    if signature == _region_signature:
        return mini(regions.size(), MAX_LOCAL_REGIONS)
    _region_signature = signature
    _clear_region_nodes()
    var count := 0
    var sorted_regions := regions.duplicate(true)
    sorted_regions.sort_custom(func(a, b): return str(a.get("id", "")) < str(b.get("id", "")))
    for region in sorted_regions:
        if typeof(region) != TYPE_DICTIONARY:
            continue
        _region_ring(region, current_region_id)
        count += 1
        if count >= MAX_LOCAL_REGIONS:
            break
    return count
