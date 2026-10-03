extends Node3D
const Catalog = preload("res://nature_asset_catalog.gd")
const Features = preload("res://world_map_features.gd")
const LiveVisual = preload("res://world_map_live_visual.gd")
const LocalMotion = preload("res://world_map_local_motion.gd")
const Hud = preload("res://world_map_hud.gd")
const Layout = preload("res://world_map_layout.gd")
const CognitiveTerrain = preload("res://world_map_cognitive_terrain.gd")
const PerceptualVegetation = preload("res://world_map_perceptual_vegetation.gd")
const EnvironmentalPalette = preload("res://world_map_environmental_palette.gd")
const PerceptualAssets = preload("res://world_map_perceptual_assets.gd")
const DistantRelief = preload("res://world_map_distant_relief.gd")
const MAP_PATH := "res://world_map_001.json"
const TILE_M := 64.0
const MAX_ACTIVE_TILES := 9
const MAX_CACHED_TILES := 24
const CENTER_DECOR_INDICES := [0, 1, 2, 3, 4, 5]
const EDGE_DECOR_INDICES := [0, 2, 4]
const CORNER_DECOR_INDICES := [1]
const MAX_ACTIVE_DECOR := 22
const LIVE_STALE_MS := 10000
const FPS_GOVERNOR_POLL_MS := 5000
const TREE_VISIBILITY_RANGE_M := 145.0
const ROCK_VISIBILITY_RANGE_M := 110.0
const PLANT_VISIBILITY_RANGE_M := 82.0
const DECOR_VISIBILITY_MARGIN_M := 12.0
const CAMERA_FAR_M := 440.0
const CAMERA_FOV_DEG := 64.0
const CAMERA_BACK_M := 6.4
const CAMERA_HEIGHT_M := 3.0
const CAMERA_LOOK_HEIGHT_M := 1.35
const CAMERA_LOOK_AHEAD_M := 11.0
const CAMERA_SHOULDER_M := 0.95
const CAMERA_MIN_GROUND_CLEARANCE_M := 1.9
const CAMERA_HEADING_MIN_STEP_M := 0.35
const CAMERA_HEADING_BLEND := 0.34
const PERCEPTUAL_CAMERA_ENABLED := true
const SHOW_DIAGNOSTIC_WORLD_OVERLAYS := false
const SHOW_TECHNICAL_STATUS := false
const SHOW_WORLD_LABELS := false
const CAMERA_COLLISION_MARGIN_M := 0.55
const ATMOSPHERIC_DEPTH_ENABLED := true
const ATMOSPHERIC_FOG_DENSITY := 0.0026
const ATMOSPHERIC_AERIAL_PERSPECTIVE := 0.32
const ATMOSPHERIC_SKY_AFFECT := 0.48
const HORIZON_GROUND_MARGIN_M := 256.0
const HORIZON_GRID := 24
const HORIZON_GROUND_OFFSET_M := 7.0
const TERRAIN_NORMAL_SAMPLE_M := 4.0
const DISTANT_VEGETATION_COUNT := 120
const DISTANT_VEGETATION_INNER_M := 96.0
const DISTANT_VEGETATION_OUTER_M := 390.0
const MIDGROUND_VEGETATION_COUNT := 180
const MIDGROUND_VEGETATION_INNER_M := 16.0
const MIDGROUND_VEGETATION_OUTER_M := 94.0
var _map: Dictionary = {}
var _catalog: RefCounted
var _layout: RefCounted
var _features: RefCounted
var _tiles: Dictionary = {}
var _tile_cache: Dictionary = {}
var _tile_cache_order: Array[String] = []
var _tile_cache_root: Node3D
var _tile_cache_hits := 0
var _tile_cache_misses := 0
var _resource_cache: Dictionary = {}
var _walker: CharacterBody3D
var _camera: Camera3D
var _camera_forward := Vector3(0.0, 0.0, -1.0)
var _horizon_ground: MeshInstance3D
var _distant_relief: RefCounted
var _distant_trunks: MultiMeshInstance3D
var _distant_canopies: MultiMeshInstance3D
var _midground_vegetation: MultiMeshInstance3D
var _perceptual_vegetation: RefCounted
var _environmental_palette: RefCounted
var _perceptual_assets: RefCounted
var _hud: CanvasLayer
var _route: Array = []
var _leg := 1
var _position := Vector3.ZERO
var _clock := 0.0
var _live_feed: Node
var _live_authoritative := false
var _live_last_update_ms := 0
var _live_region_id := ""
var _live_sequence := -1
var _live_hot_count := 0
var _live_warm_count := 0
var _live_region_count := 0
var _live_visual: RefCounted
var _cognitive_terrain: RefCounted
var _local_motion: RefCounted
var _local_surface := "terrain"
var _local_block_reason := ""
var _local_explore_enabled := false
var _last_live_position := Vector3.ZERO
var _has_live_position := false
var _render_control_path := ""
var _render_control_next_poll_ms := 0
var _decor_culling_announced := false
func _ready() -> void:
    _configure_native_fps_governor()
    var data = JSON.parse_string(FileAccess.get_file_as_string(MAP_PATH))
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != "live-infinita-visual-world-map/v1":
        push_error("MAP_BAD_MANIFEST")
        return
    _map = data
    _live_feed = get_node_or_null("LiveFeed")
    if _live_feed != null and _live_feed.has_signal("world_slice_received"):
        _live_feed.connect("world_slice_received", Callable(self, "_on_world_slice"))
    _route = _map.get("route", [])
    if _route.size() < 2:
        push_error("WORLD_MAP_PREVIEW_NO_ROUTE")
        return
    _catalog = Catalog.new()
    _layout = Layout.new(_map)
    _features = Features.new(Callable(self, "_height"), _layout.half_m)
    _features.set_landmark_markers_visible(SHOW_WORLD_LABELS)
    _live_visual = LiveVisual.new(self, _features, _map)
    _cognitive_terrain = CognitiveTerrain.new(self)
    _local_motion = LocalMotion.new(Callable(_features, "walk_height"), _layout.half_m, Callable(_cognitive_terrain, "surface_at"))
    _perceptual_vegetation = PerceptualVegetation.new(
        Callable(self, "_new_vegetation_batch"),
        Callable(self, "_height"),
        Callable(self, "_midground_allowed"),
        Callable(self, "_cell"),
        _layout.half_m,
    )
    _environmental_palette = EnvironmentalPalette.new()
    _distant_relief = DistantRelief.new()
    _perceptual_assets = PerceptualAssets.new(
        self,
        Callable(self, "_height"),
        Callable(self, "_midground_allowed"),
        Callable(self, "_cell"),
        _layout.half_m,
    )
    _tile_cache_root = Node3D.new()
    _tile_cache_root.name = "TileCache"
    _tile_cache_root.visible = false
    add_child(_tile_cache_root)
    _position = _waypoint(_route[0])
    for argument in OS.get_cmdline_user_args():
        if str(argument).begins_with("--preview-cell="):
            var parts := str(argument).trim_prefix("--preview-cell=").split(",")
            if parts.size() == 2 and parts[0].is_valid_int() and parts[1].is_valid_int():
                var x := parts[0].to_int()
                var z := parts[1].to_int()
                if x >= 0 and x < _layout.grid_size and z >= 0 and z < _layout.grid_size:
                    _position = _waypoint([x, z])
    _build_stage()
    _sync_tiles()
    _update_caption()
    print("WORLD_MAP_PREVIEW_READY grid=%dx%d m=%d tiles=%d decor=%d" % [_layout.grid_size, _layout.grid_size, _layout.world_size_m(), _tiles.size(), MAX_ACTIVE_DECOR])
func _configure_native_fps_governor() -> void:
    if OS.has_feature("web"):
        return
    _render_control_path = OS.get_environment("LIVE_INFINITA_RENDER_CONTROL_FILE")
    if _render_control_path.is_empty():
        return
    _poll_native_fps_governor()
func _poll_native_fps_governor() -> void:
    if _render_control_path.is_empty():
        return
    var now_ms := Time.get_ticks_msec()
    if now_ms < _render_control_next_poll_ms:
        return
    _render_control_next_poll_ms = now_ms + FPS_GOVERNOR_POLL_MS
    if not FileAccess.file_exists(_render_control_path):
        return
    var text_value := FileAccess.get_file_as_string(_render_control_path).strip_edges()
    if not text_value.is_valid_int():
        return
    var target_fps := clampi(text_value.to_int(), 8, 60)
    if Engine.max_fps != target_fps:
        Engine.max_fps = target_fps
func _build_stage() -> void:
    var light := DirectionalLight3D.new()
    light.rotation_degrees = Vector3(-53, 27, 0)
    light.light_energy = 1.25
    light.shadow_enabled = false
    add_child(light)
    var atmosphere := WorldEnvironment.new()
    var env := Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color("#90b9c4")
    env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color = Color("#d6e2d4")
    if ATMOSPHERIC_DEPTH_ENABLED:
        env.fog_enabled = true
        env.fog_light_color = Color("#abc4c1")
        env.fog_light_energy = 0.72
        env.fog_density = ATMOSPHERIC_FOG_DENSITY
        env.fog_aerial_perspective = ATMOSPHERIC_AERIAL_PERSPECTIVE
        env.fog_sky_affect = ATMOSPHERIC_SKY_AFFECT
    atmosphere.environment = env
    add_child(atmosphere)
    _horizon_ground = MeshInstance3D.new()
    _horizon_ground.name = "WorldHorizonGround"
    _rebuild_horizon_ground()
    add_child(_horizon_ground)
    _build_distant_vegetation()
    _build_midground_vegetation()
    _perceptual_vegetation.build(_position, _camera_forward)
    _perceptual_assets.build()
    _walker = _local_motion.create_body(self, _material(Color("#eeb74b")))
    _live_visual.build()
    _live_visual.set_diagnostic_overlays(SHOW_DIAGNOSTIC_WORLD_OVERLAYS)
    _camera = Camera3D.new()
    _camera.current = true
    _camera.far = CAMERA_FAR_M
    _camera.fov = CAMERA_FOV_DEG
    add_child(_camera)
    _hud = Hud.new()
    add_child(_hud)
    _hud.local_mode_changed.connect(_on_local_mode)
    _hud.configure(_layout.world_size_m())
    _hud.set_technical_status_visible(SHOW_TECHNICAL_STATUS)
    _follow_camera()
func _material(color: Color) -> StandardMaterial3D:
    var result := StandardMaterial3D.new()
    result.albedo_color = color
    result.roughness = 1.0
    result.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
    return result
func _environment_at(x: float, z: float) -> Dictionary:
    if _cognitive_terrain == null:
        return {}
    var value = _cognitive_terrain.call("environment_at", x, z)
    return value if typeof(value) == TYPE_DICTIONARY else {}
func _environmental_color(base: Color, x: float, z: float) -> Color:
    if _environmental_palette == null:
        return base
    return _environmental_palette.terrain_color(base, _environment_at(x, z))
func _terrain_normal(x: float, z: float) -> Vector3:
    var d := TERRAIN_NORMAL_SAMPLE_M
    var dx := (_height(x + d, z) - _height(x - d, z)) / (2.0 * d)
    var dz := (_height(x, z + d) - _height(x, z - d)) / (2.0 * d)
    return Vector3(-dx, 1.0, -dz).normalized()
func _horizon_vertex(st: SurfaceTool, x: float, z: float) -> void:
    var y:float=float(_distant_relief.visual_height(_height(x, z), x, z)) - HORIZON_GROUND_OFFSET_M
    st.set_color(_environmental_color(
        _environmental_palette.horizon_base(y), x, z
    ))
    st.set_normal(_terrain_normal(x, z))
    st.add_vertex(Vector3(x, y, z))
func _rebuild_horizon_ground() -> void:
    if _horizon_ground == null:
        return
    _distant_relief.update_observer(_position, _height(_position.x, _position.z))
    var size:=float(_layout.world_size_m()) + HORIZON_GROUND_MARGIN_M
    var origin:=-size * 0.5
    var step:=size / float(HORIZON_GRID)
    var st := SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    for z_index in range(HORIZON_GRID):
        for x_index in range(HORIZON_GRID):
            var x:=origin+float(x_index)*step
            var z:=origin+float(z_index)*step
            _horizon_vertex(st, x, z)
            _horizon_vertex(st, x + step, z)
            _horizon_vertex(st, x, z + step)
            _horizon_vertex(st, x + step, z)
            _horizon_vertex(st, x + step, z + step)
            _horizon_vertex(st, x, z + step)
    _horizon_ground.mesh = st.commit()
    var material := _material(Color.WHITE)
    material.vertex_color_use_as_albedo = true
    _horizon_ground.material_override = material
func _distant_material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 1.0
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    return material
func _new_vegetation_batch(
    name: String,
    mesh: Mesh,
    color: Color,
    instance_budget: int,
) -> MultiMeshInstance3D:
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.mesh = mesh
    multimesh.instance_count = instance_budget
    multimesh.visible_instance_count = instance_budget
    var instance := MultiMeshInstance3D.new()
    instance.name = name
    instance.multimesh = multimesh
    instance.material_override = _distant_material(color)
    add_child(instance)
    return instance
func _build_distant_vegetation() -> void:
    var trunk_mesh := CylinderMesh.new()
    trunk_mesh.top_radius = 0.26
    trunk_mesh.bottom_radius = 0.38
    trunk_mesh.height = 3.8
    trunk_mesh.radial_segments = 5
    trunk_mesh.rings = 1
    var canopy_mesh := CylinderMesh.new()
    canopy_mesh.top_radius = 0.35
    canopy_mesh.bottom_radius = 2.9
    canopy_mesh.height = 6.8
    canopy_mesh.radial_segments = 5
    canopy_mesh.rings = 1
    _distant_trunks = _new_vegetation_batch(
        "DistantTreeTrunks", trunk_mesh, Color("#6f5135"), DISTANT_VEGETATION_COUNT
    )
    _distant_canopies = _new_vegetation_batch(
        "DistantTreeCanopies", canopy_mesh, Color("#527d3f"), DISTANT_VEGETATION_COUNT
    )
    _rebuild_distant_vegetation()
func _rebuild_distant_vegetation() -> void:
    if _distant_trunks == null or _distant_canopies == null:
        return
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var seed := float(cx * 92821 + cz * 68917)
    for index in range(DISTANT_VEGETATION_COUNT):
        var phase := float(index) * 2.39996323 + sin(seed * 0.00013) * 0.8
        var ratio := sqrt((float(index) + 0.5) / float(DISTANT_VEGETATION_COUNT))
        var radius := lerpf(DISTANT_VEGETATION_INNER_M, DISTANT_VEGETATION_OUTER_M, ratio)
        radius += sin(seed * 0.00031 + float(index) * 1.73) * 13.0
        var x := clampf(_position.x + cos(phase) * radius, -_layout.half_m + 12.0, _layout.half_m - 12.0)
        var z := clampf(_position.z + sin(phase) * radius, -_layout.half_m + 12.0, _layout.half_m - 12.0)
        if _biome(_cell(x), _cell(z)) == "river":
            x = clampf(x + 24.0, -_layout.half_m + 12.0, _layout.half_m - 12.0)
        var y := _height(x, z)
        var scale_noise := 0.5 + 0.5 * sin(seed * 0.00017 + float(index) * 2.11)
        var scale := 0.82 + 0.26 * scale_noise + 0.28 * ratio
        var yaw := phase * 0.37
        var basis := Basis(Vector3.UP, yaw).scaled(Vector3(scale, scale, scale))
        _distant_trunks.multimesh.set_instance_transform(
            index, Transform3D(basis, Vector3(x, y + 1.9 * scale, z))
        )
        _distant_canopies.multimesh.set_instance_transform(
            index, Transform3D(basis, Vector3(x, y + 5.2 * scale, z))
        )
func _build_midground_vegetation() -> void:
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.16
    mesh.bottom_radius = 0.72
    mesh.height = 1.35
    mesh.radial_segments = 4
    mesh.rings = 1
    _midground_vegetation = _new_vegetation_batch(
        "MidgroundVegetation", mesh, Color("#6d9b4d"), MIDGROUND_VEGETATION_COUNT
    )
    _rebuild_midground_vegetation()
func _midground_allowed(x: float, z: float) -> bool:
    if _biome(_cell(x), _cell(z)) == "river":
        return false
    if _cognitive_terrain != null:
        var profile = _cognitive_terrain.call("decor_profile_at", x, z)
        if typeof(profile) == TYPE_DICTIONARY and not bool(profile.get("allow_decor", true)):
            return false
    return true
func _rebuild_midground_vegetation() -> void:
    if _midground_vegetation == null:
        return
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var seed := float(cx * 77191 + cz * 44893)
    var placed := 0
    var attempts := 0
    while placed < MIDGROUND_VEGETATION_COUNT and attempts < MIDGROUND_VEGETATION_COUNT * 4:
        var index := attempts
        attempts += 1
        var phase := float(index) * 2.39996323 + sin(seed * 0.00021) * 1.1
        var ratio := sqrt((float(index % MIDGROUND_VEGETATION_COUNT) + 0.5) / float(MIDGROUND_VEGETATION_COUNT))
        var radius := lerpf(MIDGROUND_VEGETATION_INNER_M, MIDGROUND_VEGETATION_OUTER_M, ratio)
        radius += sin(seed * 0.00037 + float(index) * 1.91) * 5.5
        var x := clampf(_position.x + cos(phase) * radius, -_layout.half_m + 8.0, _layout.half_m - 8.0)
        var z := clampf(_position.z + sin(phase) * radius, -_layout.half_m + 8.0, _layout.half_m - 8.0)
        if not _midground_allowed(x, z):
            continue
        var y := _height(x, z)
        var scale_noise := 0.5 + 0.5 * sin(seed * 0.00029 + float(index) * 2.37)
        var scale := 0.55 + 0.65 * scale_noise
        var basis := Basis(Vector3.UP, phase * 0.61).scaled(
            Vector3(scale, scale * (0.82 + 0.28 * scale_noise), scale)
        )
        _midground_vegetation.multimesh.set_instance_transform(
            placed, Transform3D(basis, Vector3(x, y + 0.67 * scale, z))
        )
        placed += 1

    _midground_vegetation.multimesh.visible_instance_count = placed
func _height(x: float, z: float) -> float:
    var rise := 4.0 if x > 175.0 and z < -70.0 else 1.0
    var natural := (sin(x * 0.012) * 1.8 + cos(z * 0.016) * 1.6 + sin((x + z) * 0.021) * 0.9) * rise
    var cognitive := 0.0
    if _cognitive_terrain != null:
        cognitive = float(_cognitive_terrain.call("height_delta", x, z))
    var shaped := natural + cognitive
    var bank_mix := clampf((absf(x - 32.0) - 10.0) / 20.0, 0.0, 1.0)
    return lerpf(minf(shaped, -2.3), shaped, bank_mix)
func _waypoint(cell: Array) -> Vector3:
    var flat: Vector2 = _layout.cell_center(cell)
    return Vector3(flat.x, float(_features.call("walk_height", flat.x, flat.y)), flat.y)
func _cell(value: float) -> int:
    return _layout.cell(value)
func _biome(cx: int, cz: int) -> String:
    return _layout.biome(cx, cz)
func _terrain_color(biome: String) -> Color:
    match biome:
        "river": return Color("#397eaa")
        "village": return Color("#987e5a")
        "hills": return Color("#8a9c6b")
        "clearing": return Color("#80a56b")
        "waterfall": return Color("#618f85")
        "highlands": return Color("#77866b")
        "moor": return Color("#79726c")
        "rocky": return Color("#77736d")
        "meadow": return Color("#79a95d")
        "ruins": return Color("#756d60")
        _: return Color("#52784e")
func _vertex(st: SurfaceTool, x: float, z: float) -> void:
    st.set_normal(_terrain_normal(x, z))
    st.add_vertex(Vector3(x, _height(x, z), z))
func _terrain(cx: int, cz: int, biome: String) -> MeshInstance3D:
    var st := SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    var origin: Vector2 = _layout.tile_origin(cx, cz)
    var x0 := origin.x
    var z0 := origin.y
    var step := TILE_M / 8.0
    for j in range(8):
        for i in range(8):
            var x := x0 + i * step
            var z := z0 + j * step
            _vertex(st, x, z)
            _vertex(st, x + step, z)
            _vertex(st, x, z + step)
            _vertex(st, x + step, z)
            _vertex(st, x + step, z + step)
            _vertex(st, x, z + step)
    var ground := MeshInstance3D.new()
    ground.mesh = st.commit()
    var center := origin + Vector2(TILE_M * 0.5, TILE_M * 0.5)
    var color := _environmental_color(_terrain_color(biome), center.x, center.y)
    ground.material_override = _material(color)
    return ground
func _decor_visibility_range(kind: String) -> float:
    match kind:
        "tree":
            return TREE_VISIBILITY_RANGE_M
        "rock":
            return ROCK_VISIBILITY_RANGE_M
        _:
            return PLANT_VISIBILITY_RANGE_M
func _apply_decor_culling(node: Node, range_end: float) -> int:
    var applied := 0
    if node is GeometryInstance3D:
        var geometry := node as GeometryInstance3D
        geometry.visibility_range_end = range_end
        geometry.visibility_range_end_margin = DECOR_VISIBILITY_MARGIN_M
        geometry.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
        applied += 1
    for child in node.get_children():
        applied += _apply_decor_culling(child, range_end)
    return applied
func _apply_cpu_vertex_shading(node: Node) -> int:
    var applied := 0
    if node is MeshInstance3D:
        var mesh_instance := node as MeshInstance3D
        var override_material := mesh_instance.material_override
        if override_material is BaseMaterial3D:
            var base_override := override_material as BaseMaterial3D
            base_override.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
            applied += 1
        elif mesh_instance.mesh != null:
            for surface_index in range(mesh_instance.mesh.get_surface_count()):
                var material := mesh_instance.get_surface_override_material(surface_index)
                if material == null:
                    material = mesh_instance.mesh.surface_get_material(surface_index)
                if material is BaseMaterial3D:
                    var base_material := material as BaseMaterial3D
                    base_material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
                    applied += 1
    for child in node.get_children():
        applied += _apply_cpu_vertex_shading(child)
    return applied
func _decoration(parent: Node3D, cx: int, cz: int, index: int, biome: String) -> void:
    if biome == "river":
        return
    var a := float(cx * 79 + cz * 131 + index * 47)
    var origin: Vector2 = _layout.tile_origin(cx, cz)
    var x := origin.x + 6.0 + fposmod(sin(a) * 9843.0, 52.0)
    var z := origin.y + 6.0 + fposmod(sin(a * 1.37) * 5347.0, 52.0)
    var profile: Dictionary = _cognitive_terrain.decor_profile_at(x, z)
    if not bool(profile.get("allow_decor", true)):
        return

    var kind := "tree" if index < 3 and biome != "village" else ("rock" if index % 2 == 0 else "plant")
    var influence := float(profile.get("influence", 0.0))
    var role := str(profile.get("role", "memory_field"))
    if role == "trail_edge" and influence >= 0.15 and biome != "village":
        kind = "rock" if index % 4 == 0 else "plant"
    elif influence >= 0.35 and biome != "village":
        if role == "uplift":
            kind = "rock" if index % 3 == 0 else "tree"
        elif role == "basin":
            kind = "rock" if index % 3 == 0 else "plant"

    var chosen: Dictionary = _catalog.call("pick", kind, (cx * 7 + cz * 11 + index) % 3)
    var path := str(chosen.get("path", ""))
    if path.is_empty() or not ResourceLoader.exists(path):
        return
    if not _resource_cache.has(path):
        _resource_cache[path] = load(path)
    var packed = _resource_cache[path]
    if not packed is PackedScene:
        return
    var model: Node = packed.instantiate()
    if not model is Node3D:
        model.queue_free()
        return
    var n: Node3D = model
    n.position = Vector3(x, _height(x, z), z)
    n.scale = Vector3.ONE * (0.75 if kind == "tree" else 0.90)
    var cull_range := _decor_visibility_range(kind)
    var culled_geometries := _apply_decor_culling(n, cull_range)
    _apply_cpu_vertex_shading(n)
    if culled_geometries > 0:
        n.set_meta("live_infinita_decor_cull_range_m", cull_range)
        if not _decor_culling_announced:
            _decor_culling_announced = true
            print("WORLD_MAP_DECOR_CULL tree=%.0f rock=%.0f plant=%.0f margin=%.0f" % [
                TREE_VISIBILITY_RANGE_M, ROCK_VISIBILITY_RANGE_M,
                PLANT_VISIBILITY_RANGE_M, DECOR_VISIBILITY_MARGIN_M
            ])
    parent.add_child(n)
func _prune_tile_cache() -> void:
    while _tile_cache_order.size() > MAX_CACHED_TILES:
        var stale_id: String = str(_tile_cache_order.pop_front())
        if not _tile_cache.has(stale_id):
            continue
        var stale: Node3D = _tile_cache[stale_id]
        _tile_cache.erase(stale_id)
        if is_instance_valid(stale):
            stale.queue_free()
func _cache_tile(id: String, tile: Node3D) -> void:
    if _tile_cache_root == null or not is_instance_valid(tile):
        if is_instance_valid(tile):
            tile.queue_free()
        return
    if _tile_cache.has(id):
        var existing: Node3D = _tile_cache[id]
        if is_instance_valid(existing):
            existing.queue_free()
        _tile_cache.erase(id)
        _tile_cache_order.erase(id)
    if tile.get_parent() != null:
        tile.get_parent().remove_child(tile)
    tile.visible = false
    _tile_cache_root.add_child(tile)
    _tile_cache[id] = tile
    _tile_cache_order.append(id)
    _prune_tile_cache()
func _take_cached_tile(id: String) -> Node3D:
    if not _tile_cache.has(id):
        _tile_cache_misses += 1
        return null
    var tile: Node3D = _tile_cache[id]
    _tile_cache.erase(id)
    _tile_cache_order.erase(id)
    if not is_instance_valid(tile):
        _tile_cache_misses += 1
        return null
    if tile.get_parent() != null:
        tile.get_parent().remove_child(tile)
    add_child(tile)
    tile.visible = true
    _tile_cache_hits += 1
    if _tile_cache_hits == 1 or _tile_cache_hits % 16 == 0:
        print("WORLD_MAP_TILE_CACHE hits=%d misses=%d cached=%d" % [
            _tile_cache_hits, _tile_cache_misses, _tile_cache.size()
        ])
    return tile
func _clear_tile_cache() -> void:
    for tile in _tile_cache.values():
        if is_instance_valid(tile):
            tile.queue_free()
    _tile_cache.clear()
    _tile_cache_order.clear()
    _tile_cache_hits = 0
    _tile_cache_misses = 0
func _rebuild_active_tiles() -> void:
    _clear_tile_cache()
    for id in _tiles.keys().duplicate():
        var stale: Node3D = _tiles[id]
        _tiles.erase(id)
        stale.queue_free()
    _sync_tiles()
func _decor_indices_for_tile(x: int, z: int, center_x: int, center_z: int) -> Array:
    var dx := absi(x - center_x)
    var dz := absi(z - center_z)
    var source: Array = CENTER_DECOR_INDICES
    if dx > 0 or dz > 0:
        source = EDGE_DECOR_INDICES if dx + dz == 1 else CORNER_DECOR_INDICES
    var bounded: Array = []
    for index in source:
        if int(index) < _layout.decorations_per_tile:
            bounded.append(int(index))
    return bounded
func _sync_tiles() -> void:
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var wanted := {}
    for z in range(maxi(0, cz - _layout.active_radius_tiles), mini(_layout.grid_size, cz + _layout.active_radius_tiles + 1)):
        for x in range(maxi(0, cx - _layout.active_radius_tiles), mini(_layout.grid_size, cx + _layout.active_radius_tiles + 1)):
            var id := "%d:%d" % [x, z]
            wanted[id] = true
            if _tiles.has(id):
                continue
            var cached_tile := _take_cached_tile(id)
            if cached_tile != null:
                _tiles[id] = cached_tile
                continue
            var tile := Node3D.new()
            tile.name = "Tile_%d_%d" % [x, z]
            add_child(tile)
            var biome := _biome(x, z)
            tile.add_child(_terrain(x, z, biome))
            var features: Array[String] = _features.decorate(tile, x, z, biome, _map.get("landmarks", []), _route)
            var decor_indices := _decor_indices_for_tile(x, z, cx, cz)
            print("WORLD_MAP_TILE_READY cell=%s biome=%s features=%s decor=%d" % [
                id, biome, ",".join(features), decor_indices.size()
            ])
            for i in decor_indices:
                _decoration(tile, x, z, int(i), biome)
            _tiles[id] = tile
    for id in _tiles.keys().duplicate():
        if not wanted.has(id):
            var stale: Node3D = _tiles[id]
            _tiles.erase(id)
            _cache_tile(id, stale)
    assert(_tiles.size() <= MAX_ACTIVE_TILES)
func _on_world_slice(observer: Dictionary, current_region_id: String, hot_entities: Array, warm_entities: Array, region_descriptors: Array, sequence: int, cognitive_terrain: Dictionary, environmental_state: Dictionary = {}) -> void:
    if observer.is_empty():
        return
    var first_bind := not _live_authoritative
    var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
    var perceptual_environment_changed := bool(
        _perceptual_vegetation.update_environment(environmental_state)
    )
    var asset_environment_changed := bool(
        _perceptual_assets.update_environment(environmental_state)
    )
    var environment_changed := perceptual_environment_changed or asset_environment_changed
    var terrain_changed: bool = bool(_cognitive_terrain.update(
        cognitive_terrain,
        Callable(_live_visual, "project_flat"),
        Callable(self, "_height"),
        environmental_state
    ))
    var projected: Vector3 = _live_visual.project_position(observer)
    if _has_live_position:
        _update_camera_heading(_last_live_position, projected)
    _last_live_position = projected
    _has_live_position = true
    if not _local_explore_enabled:
        _position = projected
    _live_authoritative = true
    _live_last_update_ms = Time.get_ticks_msec()
    _live_region_id = current_region_id
    _live_sequence = sequence
    var counts: Dictionary = _live_visual.update_markers(hot_entities, warm_entities)
    _live_hot_count = int(counts.get("hot", 0))
    _live_warm_count = int(counts.get("warm", 0))
    _live_region_count = _live_visual.update_regions(region_descriptors, current_region_id)
    if terrain_changed:
        _rebuild_horizon_ground()
        _rebuild_distant_vegetation()
        _rebuild_midground_vegetation()
        _rebuild_active_tiles()
    if terrain_changed or environment_changed:
        _perceptual_vegetation.rebuild(_position, _camera_forward, _live_region_id, true)
        _perceptual_assets.rebuild(_position, _camera_forward, _live_region_id, true)
        print("WORLD_MAP_MEMORY_TERRAIN projection=%s environment=%s lakes=%d trails=%d trail_batches=%d massifs=%d snow_caps=%d" % [
            _cognitive_terrain.projection_id(), _cognitive_terrain.environment_state_id(),
            _cognitive_terrain.lake_count(), _cognitive_terrain.trail_count(),
            _cognitive_terrain.trail_batch_count(), _cognitive_terrain.massif_count(),
            _cognitive_terrain.snow_cap_count()
        ])
    if not _local_explore_enabled:
        if not terrain_changed and old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
            _sync_tiles()
            _rebuild_horizon_ground()
            _rebuild_distant_vegetation()
            _rebuild_midground_vegetation()
        _perceptual_vegetation.rebuild(_position, _camera_forward, _live_region_id)
        _perceptual_assets.rebuild(_position, _camera_forward, _live_region_id)
        _follow_camera()
    _update_caption()
    if first_bind:
        print("WORLD_MAP_LIVE_BOUND region=%s sequence=%d cell=%d:%d hot=%d warm=%d regions=%d" % [_live_region_id, _live_sequence, _cell(_position.x), _cell(_position.z), _live_hot_count, _live_warm_count, _live_region_count])
func _on_local_mode(enabled: bool) -> void:
    _local_explore_enabled = enabled
    if not enabled and _has_live_position:
        var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
        _position = _last_live_position
        if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
            _sync_tiles()
            _rebuild_horizon_ground()
            _rebuild_distant_vegetation()
            _rebuild_midground_vegetation()
        _follow_camera()
    elif enabled:
        _local_motion.snap_body(_walker, _position)
    _update_caption()
func _update_camera_heading(previous: Vector3, current: Vector3) -> void:
    var flat_delta := Vector2(current.x - previous.x, current.z - previous.z)
    if flat_delta.length() < CAMERA_HEADING_MIN_STEP_M:
        return
    var desired := Vector3(flat_delta.x, 0.0, flat_delta.y).normalized()
    if _camera_forward.length_squared() < 0.001:
        _camera_forward = desired
    else:
        _camera_forward = _camera_forward.lerp(desired, CAMERA_HEADING_BLEND).normalized()
func _orient_nov_visual() -> void:
    if _walker == null or _camera_forward.length_squared() < 0.001:
        return
    _walker.rotation.y = atan2(_camera_forward.x, _camera_forward.z)
func _follow_camera(snap_body: bool = true) -> void:
    if snap_body:
        _local_motion.snap_body(_walker, _position)
    _orient_nov_visual()
    if not PERCEPTUAL_CAMERA_ENABLED:
        _camera.position = _position + Vector3(26, 32, 39)
        _camera.look_at(_position + Vector3(0, 1.0, 0))
        return
    var forward := _camera_forward.normalized()
    var target := (
        _position
        + forward * CAMERA_LOOK_AHEAD_M
        + Vector3(0, CAMERA_LOOK_HEIGHT_M, 0)
    )
    var right := Vector3(-forward.z, 0.0, forward.x).normalized()
    var camera_position := (
        _position
        - forward * CAMERA_BACK_M
        + right * CAMERA_SHOULDER_M
        + Vector3(0, CAMERA_HEIGHT_M, 0)
    )
    var camera_ground := _height(camera_position.x, camera_position.z)
    camera_position.y = maxf(
        camera_position.y,
        camera_ground + CAMERA_MIN_GROUND_CLEARANCE_M
    )

    var pivot := _position + Vector3(0.0, CAMERA_LOOK_HEIGHT_M, 0.0)
    if is_inside_tree() and get_world_3d() != null:
        var query := PhysicsRayQueryParameters3D.create(pivot, camera_position, 1)
        query.collide_with_areas = false
        query.hit_from_inside = true
        var hit := get_world_3d().direct_space_state.intersect_ray(query)
        if not hit.is_empty():
            var hit_position: Vector3 = hit.get("position", camera_position)
            var toward_pivot := (pivot - hit_position).normalized()
            if toward_pivot.length_squared() < 0.001:
                toward_pivot = forward
            camera_position = hit_position + toward_pivot * CAMERA_COLLISION_MARGIN_M
            var resolved_ground := _height(camera_position.x, camera_position.z)
            camera_position.y = maxf(
                camera_position.y,
                resolved_ground + CAMERA_MIN_GROUND_CLEARANCE_M
            )

    _camera.position = camera_position
    _camera.look_at(target)
func _update_caption() -> void:
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    if _live_authoritative and not _local_explore_enabled:
        var feed_state := str(_live_feed.get("connection_state")) if _live_feed != null else "sem feed"
        _hud.update_live(_tiles.size(), MAX_ACTIVE_DECOR, _live_region_id, _live_sequence, feed_state, cx, cz, _biome(cx, cz), _live_hot_count, _live_warm_count, _live_region_count)
    else:
        _hud.update_local(_tiles.size(), MAX_ACTIVE_DECOR, cx, cz, _biome(cx, cz), _local_surface, _local_block_reason, _local_explore_enabled)
func _process(delta: float) -> void:
    _poll_native_fps_governor()
    if _route.size() < 2:
        return
    if _live_authoritative and not _local_explore_enabled:
        var connected := _live_feed != null and str(_live_feed.get("connection_state")) == "conectado"
        if connected or Time.get_ticks_msec() - _live_last_update_ms < LIVE_STALE_MS:
            _clock += delta
            if _clock > 0.5:
                _clock = 0.0
                _update_caption()
            return
        _live_authoritative = false
        _live_region_id = ""
        _live_visual.clear_markers()
    var input := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
    var target := _waypoint(_route[_leg])
    var movement: Dictionary = _local_motion.advance(
        _position, input, target, delta, _walker, get_world_3d().direct_space_state,
        not _local_explore_enabled
    )
    var previous_position := _position
    _position = movement.get("position", _position)
    _update_camera_heading(previous_position, _position)
    _local_surface = str(movement.get("surface", "terrain"))
    _local_block_reason = str(movement.get("reason", ""))
    if bool(movement.get("reached", false)):
        _leg = (_leg + 1) % _route.size()
    if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
        _sync_tiles()
        _rebuild_horizon_ground()
        _rebuild_distant_vegetation()
        _rebuild_midground_vegetation()
    _perceptual_vegetation.rebuild(_position, _camera_forward, _live_region_id)
    _perceptual_assets.rebuild(_position, _camera_forward, _live_region_id)
    _follow_camera(false)
    _clock += delta
    if _clock > 0.3:
        _clock = 0.0
        _update_caption()
