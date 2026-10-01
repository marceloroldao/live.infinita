extends RefCounted
# Visual-only projection of bounded Memoria.ia aggregates.
# No networking, filesystem access, intents, or World State writes.

const SCHEMA := "live-infinita-cognitive-terrain/v1"
const MAX_REGIONS := 32
const MAX_TRANSITIONS := 48
const MAX_UPLIFT_M := 22.0
const MAX_BASIN_M := -12.0

var _host: Node3D
var _root: Node3D
var _projection_id := ""
var _anchors: Array = []
var _ridges: Array = []
var _lake_count := 0

func _init(host: Node3D) -> void:
    _host = host
    _root = Node3D.new()
    _root.name = "CognitiveTerrainVisuals"
    _host.add_child(_root)

func projection_id() -> String:
    return _projection_id

func lake_count() -> int:
    return _lake_count

func _clear_visuals() -> void:
    if _root == null:
        return
    for child in _root.get_children():
        child.queue_free()
    _lake_count = 0

func clear() -> bool:
    var changed := not _projection_id.is_empty() or not _anchors.is_empty() or not _ridges.is_empty()
    _projection_id = ""
    _anchors.clear()
    _ridges.clear()
    _clear_visuals()
    return changed

func _valid_policy(projection: Dictionary) -> bool:
    var policy = projection.get("policy", {})
    return (
        typeof(policy) == TYPE_DICTIONARY
        and bool(policy.get("visual_only", false))
        and policy.get("world_write_authority", true) == false
        and policy.get("selection_authority", true) == false
    )

func update(projection: Dictionary, flat_projector: Callable) -> bool:
    if (
        str(projection.get("schema", "")) != SCHEMA
        or not _valid_policy(projection)
        or not flat_projector.is_valid()
    ):
        return clear()

    var next_id := str(projection.get("projection_id", ""))
    if next_id.is_empty():
        return clear()
    if next_id == _projection_id:
        return false

    var rows = projection.get("regions", [])
    var transitions = projection.get("transitions", [])
    if (
        typeof(rows) != TYPE_ARRAY
        or rows.size() > MAX_REGIONS
        or typeof(transitions) != TYPE_ARRAY
        or transitions.size() > MAX_TRANSITIONS
    ):
        return clear()

    var next_anchors: Array = []
    var by_id: Dictionary = {}
    for item in rows:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        var row: Dictionary = item
        var region_id := str(row.get("region_id", ""))
        var center = row.get("center", {})
        if region_id.is_empty() or typeof(center) != TYPE_DICTIONARY:
            continue
        var flat_value = flat_projector.call(center)
        if typeof(flat_value) != TYPE_VECTOR2:
            continue
        var flat: Vector2 = flat_value
        var anchor := {
            "region_id": region_id,
            "position": flat,
            "bias": clampf(float(row.get("elevation_bias_m", 0.0)), MAX_BASIN_M, 18.0),
            "radius": clampf(float(row.get("influence_radius_m", 120.0)), 48.0, 240.0),
            "mass": clampf(float(row.get("cognitive_mass", 0.0)), 0.0, 1.0),
            "role": str(row.get("terrain_role", "memory_field")),
            "lake": bool(row.get("lake_candidate", false)),
        }
        next_anchors.append(anchor)
        by_id[region_id] = anchor

    var next_ridges: Array = []
    for item in transitions:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        var row: Dictionary = item
        var from_id := str(row.get("from_region_id", ""))
        var to_id := str(row.get("to_region_id", ""))
        if not by_id.has(from_id) or not by_id.has(to_id):
            continue
        var source: Dictionary = by_id[from_id]
        var target: Dictionary = by_id[to_id]
        next_ridges.append({
            "a": source["position"],
            "b": target["position"],
            "height": clampf(float(row.get("ridge_height_m", 1.0)), 0.0, 5.0),
            "width": clampf(float(row.get("ridge_width_m", 40.0)), 16.0, 96.0),
            "strength": clampf(float(row.get("strength", 0.0)), 0.0, 1.0),
        })

    _projection_id = next_id
    _anchors = next_anchors
    _ridges = next_ridges
    _rebuild_lakes()
    return true

func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 0.28
    material.metallic = 0.05
    return material

func _rebuild_lakes() -> void:
    _clear_visuals()
    for anchor in _anchors:
        if typeof(anchor) != TYPE_DICTIONARY or not bool(anchor.get("lake", false)):
            continue
        var bias := float(anchor.get("bias", 0.0))
        if bias > -6.0:
            continue
        var radius := minf(68.0, float(anchor.get("radius", 120.0)) * 0.38)
        var mesh := CylinderMesh.new()
        mesh.top_radius = radius
        mesh.bottom_radius = radius
        mesh.height = 0.12
        mesh.radial_segments = 40
        var lake := MeshInstance3D.new()
        lake.name = "MemoryLake_" + str(anchor.get("region_id", "unknown"))
        lake.mesh = mesh
        var pos: Vector2 = anchor["position"]
        lake.position = Vector3(pos.x, -1.55, pos.y)
        lake.material_override = _material(Color("#4d9db4"))
        _root.add_child(lake)
        _lake_count += 1

func surface_at(x: float, z: float) -> Dictionary:
    var point := Vector2(x, z)
    for anchor in _anchors:
        if typeof(anchor) != TYPE_DICTIONARY or not bool(anchor.get("lake", false)):
            continue
        if float(anchor.get("bias", 0.0)) > -6.0:
            continue
        var radius := minf(68.0, float(anchor.get("radius", 120.0)) * 0.38)
        var pos: Vector2 = anchor["position"]
        if point.distance_to(pos) <= radius:
            return {"walkable": false, "surface": "water", "reason": "cognitive_lake"}
    return {"walkable": true, "surface": "terrain", "reason": ""}

func decor_profile_at(x: float, z: float) -> Dictionary:
    var surface := surface_at(x, z)
    if not bool(surface.get("walkable", true)):
        return {
            "allow_decor": false,
            "role": "lake",
            "mass": 0.0,
            "influence": 1.0,
        }

    var point := Vector2(x, z)
    var best_role := "memory_field"
    var best_mass := 0.0
    var best_influence := 0.0
    for anchor in _anchors:
        if typeof(anchor) != TYPE_DICTIONARY:
            continue
        var pos: Vector2 = anchor["position"]
        var radius := maxf(1.0, float(anchor.get("radius", 120.0)))
        var d2 := point.distance_squared_to(pos)
        var falloff := exp(-0.5 * d2 / (radius * radius))
        var mass := clampf(float(anchor.get("mass", 0.0)), 0.0, 1.0)
        var influence := falloff * (0.45 + 0.55 * mass)
        if influence > best_influence:
            best_influence = influence
            best_mass = mass
            best_role = str(anchor.get("role", "memory_field"))
    return {
        "allow_decor": true,
        "role": best_role,
        "mass": best_mass,
        "influence": clampf(best_influence, 0.0, 1.0),
    }

func _segment_distance(point: Vector2, a: Vector2, b: Vector2) -> float:
    var axis := b - a
    var length_sq := axis.length_squared()
    if length_sq < 0.001:
        return point.distance_to(a)
    var t := clampf((point - a).dot(axis) / length_sq, 0.0, 1.0)
    return point.distance_to(a + axis * t)

func height_delta(x: float, z: float) -> float:
    if _anchors.is_empty():
        return 0.0
    var point := Vector2(x, z)
    var total := 0.0
    for anchor in _anchors:
        var pos: Vector2 = anchor["position"]
        var radius := maxf(1.0, float(anchor["radius"]))
        var d2 := point.distance_squared_to(pos)
        var falloff := exp(-0.5 * d2 / (radius * radius))
        total += float(anchor["bias"]) * falloff

    # Frequently repeated region transitions become low, broad ridges: a
    # geometric trace of trajectory recurrence, not a new authoritative path.
    for ridge in _ridges:
        var distance := _segment_distance(point, ridge["a"], ridge["b"])
        var width := maxf(1.0, float(ridge["width"]))
        var falloff := exp(-0.5 * distance * distance / (width * width))
        total += float(ridge["height"]) * float(ridge["strength"]) * 0.55 * falloff

    return clampf(total, MAX_BASIN_M, MAX_UPLIFT_M)
