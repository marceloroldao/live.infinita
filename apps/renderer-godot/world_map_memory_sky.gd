extends Node3D
# Stable directions from verified memory identities. No decorative random stars.
const SCHEMA := "live-infinita-memory-sky/v1"
const MAX_STARS := 256
var _world_id := ""
var _entries: Dictionary = {}
var _bodies: Dictionary = {}
var _last_generated := -1
var _batch: MultiMeshInstance3D
var _sun: MeshInstance3D
var _moon: MeshInstance3D
var _enabled := false
var _view_camera: Camera3D

func _init() -> void:
    name = "MemorySky"

func _sphere(radius: float, color: Color) -> MeshInstance3D:
    var mesh := SphereMesh.new()
    mesh.radius = radius
    mesh.height = radius * 2.0
    mesh.radial_segments = 8
    mesh.rings = 4
    var mat := StandardMaterial3D.new()
    mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    mat.albedo_color = color
    mat.disable_fog = true
    var node := MeshInstance3D.new()
    node.mesh = mesh
    node.material_override = mat
    node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    node.visible = false
    add_child(node)
    return node

func build() -> void:
    _sun = _sphere(4.0, Color("#ffe4a2"))
    _moon = _sphere(3.1, Color("#c5d4ed"))
    _sun.name = "ConfirmedMemorySun"
    _moon.name = "ConfirmedMemoryMoon"
    _batch = MultiMeshInstance3D.new()
    _batch.name = "ConfirmedMemoryStars"
    var mesh := SphereMesh.new()
    mesh.radius = 1.0
    mesh.height = 2.0
    mesh.radial_segments = 4
    mesh.rings = 1
    var mat := StandardMaterial3D.new()
    mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    mat.albedo_color = Color.WHITE
    mat.vertex_color_use_as_albedo = true
    mat.disable_fog = true
    var multi := MultiMesh.new()
    multi.transform_format = MultiMesh.TRANSFORM_3D
    multi.use_colors = true
    multi.mesh = mesh
    multi.instance_count = MAX_STARS
    _batch.multimesh = multi
    _batch.material_override = mat
    _batch.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    add_child(_batch)
    for i in range(MAX_STARS):
        multi.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ZERO), Vector3.ZERO))

func direction_for(identity: String) -> Vector3:
    # SHA gives deterministic positioning across sessions and exports.
    var digest := identity.sha256_text()
    var azimuth := float(digest.substr(0, 8).hex_to_int()) / 4294967295.0 * TAU
    var elevation := 0.12 + float(digest.substr(8, 8).hex_to_int()) / 4294967295.0 * 1.35
    return Vector3(cos(azimuth) * cos(elevation), sin(elevation), sin(azimuth) * cos(elevation))

func apply_projection(value: Dictionary) -> bool:
    if str(value.get("schema", "")) != SCHEMA or str(value.get("source", "")) != "confirmed_local_memoria_aggregate_records":
        return false
    var world := str(value.get("world_id", ""))
    var stamp = value.get("generated_at_unix")
    var rows = value.get("stars")
    var bodies = value.get("bodies")
    if world.is_empty() or typeof(stamp) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(stamp)):
        return false
    if float(stamp) > Time.get_unix_time_from_system() + 30.0 or Time.get_unix_time_from_system() - float(stamp) > 180.0:
        return false
    if typeof(rows) != TYPE_ARRAY or rows.size() > MAX_STARS or typeof(bodies) != TYPE_ARRAY or bodies.size() != 2:
        return false
    if world == _world_id and int(stamp) < _last_generated:
        return false
    var next: Dictionary = {}
    for row in rows:
        if typeof(row) != TYPE_DICTIONARY or row.get("confirmed") != true:
            return false
        var id := str(row.get("memory_id", ""))
        if not id.begins_with("external-episode:") or id.length() != 81 or not id.trim_prefix("external-episode:").is_valid_hex_number(false) or next.has(id):
            return false
        for key in ["payload_bytes", "birth_tick", "brightness", "distance"]:
            var number = row.get(key)
            if typeof(number) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(number)):
                return false
        if float(row["payload_bytes"]) <= 0.0 or float(row["birth_tick"]) < 0.0 or float(row["brightness"]) < 0.0 or float(row["brightness"]) > 1.0 or float(row["distance"]) < 1.0:
            return false
        next[id] = row.duplicate(true)
    var next_bodies: Dictionary = {}
    for row in bodies:
        if typeof(row) != TYPE_DICTIONARY or row.get("confirmed") != true or str(row.get("provenance", "")) != "world_celestial_definition":
            return false
        var body := str(row.get("body", ""))
        var id := str(row.get("memory_id", ""))
        if body not in ["sun", "moon"] or next_bodies.has(body) or not id.begins_with("structural-event:") or id.length() != 57 or not id.trim_prefix("structural-event:").is_valid_hex_number(false):
            return false
        next_bodies[body] = row.duplicate(true)
    if world != _world_id:
        _entries.clear()
    # Retain prior identity fades; same-star refresh never resets brightness to zero.
    for id in next:
        next[id]["fade"] = float(_entries.get(id, {}).get("fade", 0.0))
    _entries = next
    _bodies = next_bodies
    _world_id = world
    _last_generated = int(stamp)
    _enabled = true
    return true

func update_view(camera: Camera3D, cycle: RefCounted, delta: float) -> void:
    if _batch == null or camera == null:
        return
    _view_camera = camera
    global_position = camera.global_position
    var state: Dictionary = cycle.sample()
    var night := 1.0 - float(state["daylight"])
    var fresh := Time.get_unix_time_from_system() - float(_last_generated) <= 180.0
    var show: bool = _enabled and fresh and bool(state["synced"]) and cycle._world_id == _world_id
    _batch.visible = show and night > 0.0001
    var phase := float(state["phase"])
    var angle := phase * TAU - PI * 0.5
    var sun_direction := Vector3(cos(angle), sin(angle), 0.25).normalized()
    _sun.position = sun_direction * 180.0
    _moon.position = -sun_direction * 180.0
    _sun.visible = show and _bodies.has("sun") and sun_direction.y > -0.05
    _moon.visible = show and _bodies.has("moon") and sun_direction.y < 0.05
    var index := 0
    for id in _entries:
        var entry: Dictionary = _entries[id]
        var brightness := float(entry["brightness"])
        # Faint distant memories stay invisible; threshold has no artificial floor.
        var target := clampf((brightness - 0.009) / 0.04, 0.0, 1.0) * night if show else 0.0
        entry["fade"] = move_toward(float(entry["fade"]), target, maxf(0.0, delta) / 5.0)
        var fade := float(entry["fade"])
        var radius := clampf(sqrt(brightness) * 0.26, 0.015, 0.26) * fade
        var transform := Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * radius), direction_for(id) * 160.0)
        _batch.multimesh.set_instance_transform(index, transform)
        _batch.multimesh.set_instance_color(index, Color(0.85, 0.9, 1.0) * clampf(brightness * 5.0, 0.0, 1.0))
        index += 1
    for i in range(index, MAX_STARS):
        _batch.multimesh.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ZERO), Vector3.ZERO))

func _process(_delta: float) -> void:
    # Parent preview moves the camera before child processing: keep the sky centered.
    if is_instance_valid(_view_camera):
        global_position = _view_camera.global_position
