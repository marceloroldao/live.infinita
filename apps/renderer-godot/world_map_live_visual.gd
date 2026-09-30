extends RefCounted

const MAX_HOT_MARKERS := 96
const MAX_WARM_MARKERS := 192
const HALF := 512.0

var _host: Node3D
var _features: RefCounted
var _map: Dictionary
var _hot_markers: MultiMeshInstance3D
var _warm_markers: MultiMeshInstance3D

func _init(host: Node3D, features: RefCounted, map_data: Dictionary) -> void:
    _host = host
    _features = features
    _map = map_data

func build() -> void:
    _hot_markers = _marker_batch("HotEntities", Color("#ec764f"), 0.40)
    _warm_markers = _marker_batch("WarmEntities", Color("#65a9c8"), 0.24)

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

func project_position(position_data: Dictionary) -> Vector3:
    var projection = _map.get("runtime_projection", {})
    var world_point := Vector2(float(position_data.get("x", 640.0)), float(position_data.get("y", 360.0)))
    if typeof(projection) != TYPE_DICTIONARY:
        var fallback := world_point - Vector2(640.0, 360.0)
        return Vector3(fallback.x, float(_features.call("walk_height", fallback.x, fallback.y)), fallback.y)
    var wa := _array_vec2(projection.get("world_anchor_a", []), Vector2(350, 340))
    var wb := _array_vec2(projection.get("world_anchor_b", []), Vector2(930, 390))
    var ma := _array_vec2(projection.get("map_anchor_a_m", []), Vector2(-160, -32))
    var mb := _array_vec2(projection.get("map_anchor_b_m", []), Vector2(-352, -32))
    var world_axis := wb - wa
    var map_axis := mb - ma
    if world_axis.length() < 0.001 or map_axis.length() < 0.001:
        return Vector3(ma.x, float(_features.call("walk_height", ma.x, ma.y)), ma.y)
    var wu := world_axis.normalized()
    var wp := Vector2(-wu.y, wu.x)
    var mu := map_axis.normalized()
    var sign := float(projection.get("perpendicular_sign", 1.0))
    var mp := Vector2(-mu.y, mu.x) * sign
    var scale := map_axis.length() / world_axis.length()
    var offset := world_point - wa
    var mapped := ma + mu * offset.dot(wu) * scale + mp * offset.dot(wp) * scale
    mapped.x = clampf(mapped.x, -HALF + 1.0, HALF - 1.0)
    mapped.y = clampf(mapped.y, -HALF + 1.0, HALF - 1.0)
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
