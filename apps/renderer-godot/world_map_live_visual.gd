extends RefCounted

const MAX_HOT_MARKERS := 96
const MAX_WARM_MARKERS := 192
const MAX_LOCAL_REGIONS := 16
const MAX_REGION_LABELS := 4
const REGION_RING_SEGMENTS := 48

var _host: Node3D
var _features: RefCounted
var _map: Dictionary
var _hot_markers: MultiMeshInstance3D
var _warm_markers: MultiMeshInstance3D
var _region_root: Node3D
var _region_signature := ""
var _diagnostic_overlays_enabled := true
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

func set_diagnostic_overlays(enabled: bool) -> void:
    if _diagnostic_overlays_enabled == enabled:
        return
    _diagnostic_overlays_enabled = enabled
    _region_signature = ""
    _clear_region_nodes()

func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 1.0
    material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
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
        _region_root.remove_child(child)
        child.queue_free()

func _region_material(color: Color) -> StandardMaterial3D:
    var material := _material(color)
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    return material

func _append_region_ring(mesh: ImmediateMesh, region: Dictionary) -> bool:
    var center_data = region.get("center", {})
    if typeof(center_data) != TYPE_DICTIONARY:
        return false
    var radius := maxf(1.0, float(region.get("radius", 1.0)) * _projection_scale())
    var center := project_position(center_data)
    for index in range(REGION_RING_SEGMENTS):
        var angle_a := TAU * float(index) / float(REGION_RING_SEGMENTS)
        var angle_b := TAU * float(index + 1) / float(REGION_RING_SEGMENTS)
        var ax := center.x + cos(angle_a) * radius
        var az := center.z + sin(angle_a) * radius
        var bx := center.x + cos(angle_b) * radius
        var bz := center.z + sin(angle_b) * radius
        var ay := float(_features.call("walk_height", ax, az)) + 0.16
        var by := float(_features.call("walk_height", bx, bz)) + 0.16
        mesh.surface_add_vertex(Vector3(ax, ay, az))
        mesh.surface_add_vertex(Vector3(bx, by, bz))
    return true

func _build_region_rings(regions: Array, current_region_id: String) -> int:
    var mesh := ImmediateMesh.new()
    var surfaces := 0
    var normal_regions: Array = []
    var current_regions: Array = []
    for region in regions:
        if str(region.get("id", "")) == current_region_id:
            current_regions.append(region)
        else:
            normal_regions.append(region)

    if not normal_regions.is_empty():
        mesh.surface_begin(
            Mesh.PRIMITIVE_LINES,
            _region_material(Color("#88b7a0"))
        )
        for region in normal_regions:
            _append_region_ring(mesh, region)
        mesh.surface_end()
        surfaces += 1

    if not current_regions.is_empty():
        mesh.surface_begin(
            Mesh.PRIMITIVE_LINES,
            _region_material(Color("#f4d35e"))
        )
        for region in current_regions:
            _append_region_ring(mesh, region)
        mesh.surface_end()
        surfaces += 1

    if surfaces > 0:
        var ring_batch := MeshInstance3D.new()
        ring_batch.name = "RegionRings"
        ring_batch.mesh = mesh
        _region_root.add_child(ring_batch)
    return surfaces

func _region_label(region: Dictionary, current_region_id: String) -> Label3D:
    var center_data = region.get("center", {})
    if typeof(center_data) != TYPE_DICTIONARY:
        return null
    var center := project_position(center_data)
    var current := str(region.get("id", "")) == current_region_id
    var color := Color("#f4d35e") if current else Color("#88b7a0")
    var label := Label3D.new()
    var metadata = region.get("metadata", {})
    var title := str(region.get("id", "region"))
    if typeof(metadata) == TYPE_DICTIONARY:
        title = str(metadata.get("label", title))
    label.name = "RegionLabel_" + str(region.get("id", "unknown"))
    label.text = title
    label.position = center + Vector3(0, 2.4, 0)
    label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
    label.font_size = 24 if current else 18
    label.pixel_size = 0.012
    label.modulate = color
    return label

func _build_region_labels(regions: Array, current_region_id: String) -> int:
    var current_position := Vector2.ZERO
    var has_current := false
    for region in regions:
        if str(region.get("id", "")) != current_region_id:
            continue
        var center_data = region.get("center", {})
        if typeof(center_data) != TYPE_DICTIONARY:
            continue
        var center := project_position(center_data)
        current_position = Vector2(center.x, center.z)
        has_current = true
        break

    var ranked: Array = []
    for region in regions:
        var center_data = region.get("center", {})
        if typeof(center_data) != TYPE_DICTIONARY:
            continue
        var center := project_position(center_data)
        var is_current := str(region.get("id", "")) == current_region_id
        var distance := 0.0
        if has_current and not is_current:
            distance = Vector2(center.x, center.z).distance_to(current_position)
        ranked.append({
            "region": region,
            "current": is_current,
            "distance": distance,
        })

    ranked.sort_custom(func(a, b):
        if bool(a.get("current", false)) != bool(b.get("current", false)):
            return bool(a.get("current", false))
        var da := float(a.get("distance", 0.0))
        var db := float(b.get("distance", 0.0))
        if not is_equal_approx(da, db):
            return da < db
        return str(a["region"].get("id", "")) < str(b["region"].get("id", ""))
    )

    var labels := 0
    for item in ranked:
        if labels >= MAX_REGION_LABELS:
            break
        var label := _region_label(item["region"], current_region_id)
        if label == null:
            continue
        _region_root.add_child(label)
        labels += 1
    return labels

func update_regions(regions: Array, current_region_id: String) -> int:
    if not _diagnostic_overlays_enabled:
        if _region_root != null and _region_root.get_child_count() > 0:
            _clear_region_nodes()
        return mini(regions.size(), MAX_LOCAL_REGIONS)
    var signature := _region_signature_for(regions, current_region_id)
    if signature == _region_signature:
        return mini(regions.size(), MAX_LOCAL_REGIONS)
    _region_signature = signature
    _clear_region_nodes()

    var sorted_regions := regions.duplicate(true)
    sorted_regions.sort_custom(func(a, b): return str(a.get("id", "")) < str(b.get("id", "")))
    var selected: Array = []
    for region in sorted_regions:
        if typeof(region) != TYPE_DICTIONARY:
            continue
        selected.append(region)
        if selected.size() >= MAX_LOCAL_REGIONS:
            break

    var surfaces := _build_region_rings(selected, current_region_id)
    var labels := _build_region_labels(selected, current_region_id)
    print("WORLD_MAP_REGION_VISUAL rings=%d surfaces=%d labels=%d" % [
        selected.size(), surfaces, labels
    ])
    return selected.size()
