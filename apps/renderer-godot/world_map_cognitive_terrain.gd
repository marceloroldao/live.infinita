extends RefCounted
# Visual-only projection of bounded Memoria.ia aggregates.
# No networking, filesystem access, intents, or World State writes.

const SCHEMA := "live-infinita-cognitive-terrain/v1"
const MAX_REGIONS := 32
const MAX_TRANSITIONS := 48
const MAX_SPATIAL_TRAILS := 128
const MAX_UPLIFT_M := 22.0
const MAX_BASIN_M := -12.0
const MAX_TRAIL_SEGMENTS := 192
const MAX_TRAIL_MEANDER_M := 4.5
const TRAIL_MEANDER_DISTANCE_RATIO := 0.055
const MAX_MASSIFS := 6
const MAX_MASSIF_HEIGHT_M := 68.0
const MASSIF_MIN_BIAS_M := 6.0
const MASSIF_MIN_MASS := 0.55

var _host: Node3D
var _root: Node3D
var _projection_id := ""
var _anchors: Array = []
var _ridges: Array = []
var _spatial_trails: Array = []
var _lake_count := 0
var _trail_count := 0
var _trail_batch_count := 0
var _massif_count := 0

func _init(host: Node3D) -> void:
    _host = host
    _root = Node3D.new()
    _root.name = "CognitiveTerrainVisuals"
    _host.add_child(_root)

func projection_id() -> String:
    return _projection_id

func lake_count() -> int:
    return _lake_count

func trail_count() -> int:
    return _trail_count

func trail_batch_count() -> int:
    return _trail_batch_count

func massif_count() -> int:
    return _massif_count

func _clear_visuals() -> void:
    if _root == null:
        return
    for child in _root.get_children():
        child.queue_free()
    _lake_count = 0
    _trail_count = 0
    _trail_batch_count = 0
    _massif_count = 0

func clear() -> bool:
    var changed := not _projection_id.is_empty() or not _anchors.is_empty() or not _ridges.is_empty() or not _spatial_trails.is_empty()
    _projection_id = ""
    _anchors.clear()
    _ridges.clear()
    _spatial_trails.clear()
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

func update(projection: Dictionary, flat_projector: Callable, height_sampler: Callable = Callable()) -> bool:
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
    var spatial_trails = projection.get("spatial_trails", [])
    if (
        typeof(rows) != TYPE_ARRAY
        or rows.size() > MAX_REGIONS
        or typeof(transitions) != TYPE_ARRAY
        or transitions.size() > MAX_TRANSITIONS
        or typeof(spatial_trails) != TYPE_ARRAY
        or spatial_trails.size() > MAX_SPATIAL_TRAILS
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
            "count": maxi(0, int(row.get("count", 0))),
            "trail_strength": clampf(float(row.get("trail_strength", 0.0)), 0.0, 1.0),
            "trail_candidate": bool(row.get("trail_candidate", false)),
            "trail_width": clampf(float(row.get("trail_width_m", 0.7)), 0.4, 3.0),
        })

    var next_spatial_trails: Array = []
    for item in spatial_trails:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        var row: Dictionary = item
        if not bool(row.get("trail_candidate", false)):
            continue
        var from_position = row.get("from_position", {})
        var to_position = row.get("to_position", {})
        if typeof(from_position) != TYPE_DICTIONARY or typeof(to_position) != TYPE_DICTIONARY:
            continue
        var a_value = flat_projector.call(from_position)
        var b_value = flat_projector.call(to_position)
        if typeof(a_value) != TYPE_VECTOR2 or typeof(b_value) != TYPE_VECTOR2:
            continue
        next_spatial_trails.append({
            "a": a_value,
            "b": b_value,
            "count": maxi(0, int(row.get("count", 0))),
            "trail_strength": clampf(float(row.get("trail_strength", 0.0)), 0.0, 1.0),
            "trail_candidate": true,
            "trail_width": clampf(float(row.get("trail_width_m", 0.7)), 0.4, 3.0),
        })

    _projection_id = next_id
    _anchors = next_anchors
    _ridges = next_ridges
    _spatial_trails = next_spatial_trails
    _rebuild_lakes()
    _rebuild_massifs(height_sampler)
    _rebuild_trails(height_sampler)
    return true

func _material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 0.28
    material.metallic = 0.05
    material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
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

func _massif_material(mass: float, secondary: bool = false) -> StandardMaterial3D:
    var low := Color("#5f665d")
    var high := Color("#899083")
    var color := low.lerp(high, clampf(mass, 0.0, 1.0))
    if secondary:
        color = color.darkened(0.08)
    var material := _material(color)
    material.roughness = 1.0
    material.metallic = 0.0
    return material

func _add_massif_peak(
    region_id: String,
    suffix: String,
    center: Vector2,
    radius: float,
    height: float,
    mass: float,
    height_sampler: Callable,
    secondary: bool = false,
) -> void:
    var ground_y := 0.0
    if height_sampler.is_valid():
        ground_y = float(height_sampler.call(center.x, center.y))
    var mesh := CylinderMesh.new()
    mesh.top_radius = maxf(1.2, radius * 0.07)
    mesh.bottom_radius = radius
    mesh.height = height
    mesh.radial_segments = 9
    mesh.rings = 2
    var peak := MeshInstance3D.new()
    peak.name = "MemoryMassif_%s_%s" % [region_id, suffix]
    peak.mesh = mesh
    peak.position = Vector3(center.x, ground_y + height * 0.5 - 0.15, center.y)
    peak.rotation.y = sin(center.x * 0.021 + center.y * 0.017) * 0.38
    peak.material_override = _massif_material(mass, secondary)
    _root.add_child(peak)

func _rebuild_massifs(height_sampler: Callable) -> void:
    for anchor in _anchors:
        if _massif_count >= MAX_MASSIFS:
            break
        if typeof(anchor) != TYPE_DICTIONARY or bool(anchor.get("lake", false)):
            continue
        var bias := float(anchor.get("bias", 0.0))
        var mass := clampf(float(anchor.get("mass", 0.0)), 0.0, 1.0)
        if bias < MASSIF_MIN_BIAS_M or mass < MASSIF_MIN_MASS:
            continue
        var pos: Vector2 = anchor["position"]
        var influence_radius := float(anchor.get("radius", 120.0))
        var base_radius := clampf(influence_radius * 0.30, 24.0, 62.0)
        var peak_height := clampf(
            bias * 2.2 + mass * 24.0,
            20.0,
            MAX_MASSIF_HEIGHT_M
        )
        var seed := sin(pos.x * 0.019 + pos.y * 0.023 + mass * 2.7)
        var angle := seed * PI
        var axis := Vector2(cos(angle), sin(angle))
        var ortho := Vector2(-axis.y, axis.x)
        var region_id := str(anchor.get("region_id", "unknown"))
        _add_massif_peak(
            region_id, "Primary", pos,
            base_radius, peak_height, mass, height_sampler, false
        )
        _add_massif_peak(
            region_id, "SecondaryA",
            pos + axis * base_radius * 0.34,
            base_radius * 0.56,
            peak_height * (0.62 + 0.06 * mass),
            mass,
            height_sampler,
            true
        )
        _add_massif_peak(
            region_id, "SecondaryB",
            pos - axis * base_radius * 0.20 + ortho * base_radius * 0.28,
            base_radius * 0.44,
            peak_height * (0.46 + 0.08 * mass),
            mass,
            height_sampler,
            true
        )
        _massif_count += 1

func _trail_batch_material() -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = Color.WHITE
    material.vertex_color_use_as_albedo = true
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
    material.roughness = 1.0
    material.metallic = 0.0
    return material

func _trail_vertex_color(intensity: float) -> Color:
    var weak := Color("#a18a67")
    var strong := Color("#725437")
    return weak.lerp(strong, clampf(intensity, 0.0, 1.0))

func _trail_orientation_sign(a: Vector2, b: Vector2) -> float:
    if a.x < b.x:
        return 1.0
    if a.x > b.x:
        return -1.0
    return 1.0 if a.y <= b.y else -1.0

func _trail_seed(a: Vector2, b: Vector2) -> float:
    # Symmetric in the endpoints so a→b and b→a render the same geometry.
    return sin((a.x + b.x) * 0.013 + (a.y + b.y) * 0.017)

func _natural_trail_point(
    a: Vector2,
    b: Vector2,
    t: float,
    count: int,
    intensity: float,
) -> Vector2:
    var clamped_t := clampf(t, 0.0, 1.0)
    var axis := b - a
    var distance := axis.length()
    if distance < 0.001:
        return a
    var normal := Vector2(-axis.y, axis.x) / distance
    var recurrence := clampf(float(maxi(count, 2) - 2) / 10.0, 0.0, 1.0)
    var strength := clampf(intensity, 0.0, 1.0)
    var amplitude := minf(MAX_TRAIL_MEANDER_M, distance * TRAIL_MEANDER_DISTANCE_RATIO)
    # Repeated, strong routes gradually straighten without ever changing endpoints.
    amplitude *= lerpf(1.0, 0.58, recurrence)
    amplitude *= lerpf(1.0, 0.72, strength)
    var envelope := sin(PI * clamped_t)
    var s_curve := sin(TAU * clamped_t)
    var seed := _trail_seed(a, b)
    var orientation := _trail_orientation_sign(a, b)
    var bend := orientation * (0.58 + 0.18 * seed)
    var meander := (0.24 + 0.08 * absf(seed)) * s_curve
    var offset := amplitude * envelope * (bend + meander)
    return a.lerp(b, clamped_t) + normal * offset

func _trail_height(point: Vector2, height_sampler: Callable) -> float:
    var y := height_delta(point.x, point.y)
    if height_sampler.is_valid():
        y = float(height_sampler.call(point.x, point.y))
    return y + 0.08

func _rebuild_trails(height_sampler: Callable) -> void:
    var built_segments := 0
    var surface := SurfaceTool.new()
    surface.begin(Mesh.PRIMITIVE_TRIANGLES)
    var trail_source: Array = _spatial_trails if not _spatial_trails.is_empty() else _ridges
    for ridge in trail_source:
        if built_segments >= MAX_TRAIL_SEGMENTS:
            break
        if typeof(ridge) != TYPE_DICTIONARY:
            continue
        if not bool(ridge.get("trail_candidate", false)) or int(ridge.get("count", 0)) < 2:
            continue
        var intensity := clampf(float(ridge.get("trail_strength", 0.0)), 0.0, 1.0)
        if intensity < 0.18:
            continue
        var a: Vector2 = ridge["a"]
        var b: Vector2 = ridge["b"]
        var distance := a.distance_to(b)
        if distance < 0.5:
            continue
        var count := maxi(2, int(ridge.get("count", 0)))
        var segments := clampi(int(ceil(distance / 12.0)), 1, 16)
        var width := clampf(float(ridge.get("trail_width", 0.7)), 0.4, 3.0)
        var color := _trail_vertex_color(intensity)
        var built_for_trail := 0
        for index in range(segments):
            if built_segments >= MAX_TRAIL_SEGMENTS:
                break
            var t0 := float(index) / float(segments)
            var t1 := float(index + 1) / float(segments)
            var p0 := _natural_trail_point(a, b, t0, count, intensity)
            var p1 := _natural_trail_point(a, b, t1, count, intensity)
            var axis := p1 - p0
            var length := axis.length()
            if length < 0.05:
                continue
            var normal := Vector2(-axis.y, axis.x) / length * (width * 0.5)
            var p0l := p0 + normal
            var p0r := p0 - normal
            var p1l := p1 + normal
            var p1r := p1 - normal
            var vertices: Array[Vector3] = [
                Vector3(p0l.x, _trail_height(p0l, height_sampler), p0l.y),
                Vector3(p0r.x, _trail_height(p0r, height_sampler), p0r.y),
                Vector3(p1l.x, _trail_height(p1l, height_sampler), p1l.y),
                Vector3(p1l.x, _trail_height(p1l, height_sampler), p1l.y),
                Vector3(p0r.x, _trail_height(p0r, height_sampler), p0r.y),
                Vector3(p1r.x, _trail_height(p1r, height_sampler), p1r.y),
            ]
            for vertex in vertices:
                surface.set_color(color)
                surface.add_vertex(vertex)
            built_segments += 1
            built_for_trail += 1
        if built_for_trail > 0:
            _trail_count += 1

    if built_segments == 0:
        return
    var trail_batch := MeshInstance3D.new()
    trail_batch.name = "MemoryTrailBatch"
    trail_batch.mesh = surface.commit()
    trail_batch.material_override = _trail_batch_material()
    _root.add_child(trail_batch)
    _trail_batch_count = 1

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

func _trail_decor_profile(point: Vector2) -> Dictionary:
    var best_edge_influence := 0.0
    for trail in _spatial_trails:
        if typeof(trail) != TYPE_DICTIONARY:
            continue
        if not bool(trail.get("trail_candidate", false)):
            continue
        var intensity := clampf(float(trail.get("trail_strength", 0.0)), 0.0, 1.0)
        if intensity < 0.18:
            continue
        var a: Vector2 = trail["a"]
        var b: Vector2 = trail["b"]
        var distance := a.distance_to(b)
        if distance < 0.5:
            continue
        var count := maxi(2, int(trail.get("count", 0)))
        var segments := clampi(int(ceil(distance / 12.0)), 1, 16)
        var trail_distance := 1.0e20
        for index in range(segments):
            var t0 := float(index) / float(segments)
            var t1 := float(index + 1) / float(segments)
            var p0 := _natural_trail_point(a, b, t0, count, intensity)
            var p1 := _natural_trail_point(a, b, t1, count, intensity)
            trail_distance = minf(trail_distance, _segment_distance(point, p0, p1))

        var width := clampf(float(trail.get("trail_width", 0.7)), 0.4, 3.0)
        var recurrence := clampf(float(count - 2) / 10.0, 0.0, 1.0)
        var core_radius := clampf(
            0.65 + width * (0.70 + 0.35 * intensity) + 0.35 * recurrence,
            0.9,
            4.0
        )
        var edge_radius := clampf(
            core_radius + 1.8 + 1.2 * intensity,
            core_radius + 1.0,
            7.0
        )
        if trail_distance <= core_radius:
            return {
                "allow_decor": false,
                "role": "trail_corridor",
                "mass": 0.0,
                "influence": 1.0,
                "trail_distance_m": trail_distance,
                "trail_clearance_m": core_radius,
            }
        if trail_distance < edge_radius:
            var edge_influence := 1.0 - (
                (trail_distance - core_radius) / maxf(0.001, edge_radius - core_radius)
            )
            best_edge_influence = maxf(best_edge_influence, edge_influence)

    if best_edge_influence > 0.0:
        return {
            "allow_decor": true,
            "role": "trail_edge",
            "mass": 0.0,
            "influence": clampf(best_edge_influence, 0.0, 1.0),
        }
    return {
        "allow_decor": true,
        "role": "memory_field",
        "mass": 0.0,
        "influence": 0.0,
    }

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
    var trail_profile := _trail_decor_profile(point)
    if not bool(trail_profile.get("allow_decor", true)):
        return trail_profile

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

    if str(trail_profile.get("role", "")) == "trail_edge":
        return trail_profile
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
