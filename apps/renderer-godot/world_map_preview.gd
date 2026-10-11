extends Node3D
const Catalog = preload("res://nature_asset_catalog.gd")
const Features = preload("res://world_map_features.gd")
const LiveVisual = preload("res://world_map_live_visual.gd")
const LocalMotion = preload("res://world_map_local_motion.gd")
const Hud = preload("res://world_map_hud.gd")
const LiveProgramOverlay = preload("res://live_program_overlay.gd")
const LiveProgramAudio = preload("res://live_program_audio.gd")
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
const Residency = preload("res://nature_local_residency.gd")
const LOCAL_STABLE_RADIUS_M := 45.0
var _midground_residency = Residency.new()
var _distant_residency = Residency.new()
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
var _route_goal = preload("res://nov_route_goal.gd").new()
var _stuck_recovery = preload("res://nov_stuck_recovery.gd").new()
var _recovery_pending := false
var _recovery_start := Vector3.ZERO
var _camera_stabilizer = preload("res://nov_camera_stabilizer.gd").new()
var _horizon_ground: MeshInstance3D
var _distant_relief: RefCounted
var _distant_trunks: MultiMeshInstance3D
var _distant_canopies: MultiMeshInstance3D
var _midground_vegetation: MultiMeshInstance3D
var _perceptual_vegetation: RefCounted
var _environmental_palette: RefCounted
var _perceptual_assets: RefCounted
var _hud: CanvasLayer
var _program_overlay: CanvasLayer
var _route: Array = []
var _leg := 1
var _position := Vector3.ZERO
var _clock := 0.0
var _day_cycle = preload("res://world_map_day_cycle.gd").new()
var _day_environment: Environment
var _day_light: DirectionalLight3D
var _memory_sky: Node3D
var _visual_perception = preload("res://nov_visual_perception.gd").new()
var _encounters = preload("res://nov_animal_encounters.gd").new()
var _animal_search_intent = preload("res://nov_animal_search_intent.gd").new()
var _animal_search_selection: Dictionary = {}
var _animal_search_route := ""
var _wildlife: Node3D
var _perception_elapsed := 0.0
var _perception_announced := false
var _physical_weather: Node3D
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
var _live_walk_velocity := Vector2.ZERO
const LIVE_WALK_SPEED_MPS := 8.0
const LIVE_WALK_ACCEL_MPS2 := 18.0
var _render_control_path := ""
var _render_control_next_poll_ms := 0
var _decor_culling_announced := false
# Consolidated inference samples shared by every tile and surface consumer.
# Session lifetime: do not mutate a vertex already used by physical presentation.
var _consolidated_ground: Dictionary = {}
var _ground_consolidation = preload("res://nov_ground_consolidation.gd").new()
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
    if _live_feed != null and _live_feed.has_signal("sky_clock_received"):
        _live_feed.sky_clock_received.connect(Callable(_day_cycle, "apply_clock"))
    _wildlife = preload("res://world_map_wildlife.gd").new()
    add_child(_wildlife)
    var wildlife_state := OS.get_environment("LIVE_INFINITA_WILDLIFE_STATE")
    var wildlife_public := OS.get_environment("LIVE_INFINITA_WILDLIFE_PUBLIC")
    var wildlife_authority := not OS.has_feature("web") and not OS.get_cmdline_user_args().has("--offline-tour") and not wildlife_state.is_empty() and not wildlife_public.is_empty()
    _wildlife.configure(wildlife_authority,wildlife_state,wildlife_public)
    if wildlife_authority:
        _encounters.configure(OS.get_environment("LIVE_INFINITA_ENCOUNTERS_STATE"),OS.get_environment("LIVE_INFINITA_ENCOUNTERS_ACK"))
        _visual_perception.observation_ready.connect(Callable(_encounters,"observe"))
        if OS.get_environment("LIVE_INFINITA_ANIMAL_SEARCH_ENABLED")=="1":
            _animal_search_intent.configure(OS.get_environment("LIVE_INFINITA_ANIMAL_SEARCH_POLICY"),OS.get_environment("LIVE_INFINITA_ANIMAL_SEARCH_PUBLIC"),OS.get_environment("LIVE_INFINITA_ANIMAL_SEARCH_SOURCE"),_encounters._session)
            _visual_perception.observation_ready.connect(Callable(_animal_search_intent,"observe"))
    _wildlife._habitat_allowed = Callable(self,"_midground_allowed")
    _physical_weather = preload("res://world_map_weather.gd").new()
    add_child(_physical_weather)
    _physical_weather.build()
    if _live_feed != null and _live_feed.has_signal("physical_weather_received"):
        _live_feed.physical_weather_received.connect(Callable(_physical_weather,"apply_weather"))
    _memory_sky = preload("res://world_map_memory_sky.gd").new()
    add_child(_memory_sky)
    _memory_sky.build()
    if _live_feed != null and _live_feed.has_signal("memory_sky_received"):
        _live_feed.memory_sky_received.connect(Callable(_memory_sky, "apply_projection"))
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
    _local_motion.inertial_enabled = OS.get_environment("LIVE_INFINITA_NOV_INERTIAL_MOTION")=="1" or bool(ProjectSettings.get_setting("live_infinita/nov_inertial_motion",false))
    if _live_feed != null and _live_feed.has_signal("navigation_context_received"):
        _live_feed.navigation_context_received.connect(Callable(_local_motion._episodes, "set_context"))
        _live_feed.navigation_context_received.connect(Callable(_local_motion._experience.working_memory, "set_context"))
        _live_feed.navigation_context_received.connect(Callable(_local_motion._pattern_collector, "set_context"))
    var navigation_recall = preload("res://nov_navigation_recall.gd").new()
    navigation_recall.name = "NavigationRecall"
    navigation_recall.snapshot_ready.connect(Callable(_local_motion._experience, "apply_recall"))
    navigation_recall.learning_status_ready.connect(Callable(_local_motion._experience, "apply_learning_status"))
    add_child(navigation_recall)
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
    _recovery_start = _position
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
    _day_light = light
    light.rotation_degrees = Vector3(-53, 27, 0)
    light.light_energy = 1.25
    light.shadow_enabled = false
    add_child(light)
    var atmosphere := WorldEnvironment.new()
    var env := Environment.new()
    _day_environment = env
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
    _program_overlay = LiveProgramOverlay.new()
    add_child(_program_overlay)
    if _live_feed != null:
        _live_feed.connect("program_state_received", Callable(_program_overlay, "apply_program_state"))
        _live_feed.connect("audience_event_received", Callable(_program_overlay, "apply_audience_event"))
    LiveProgramAudio.install()
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
    # Split coarse patches along the active-tile boundary, leaving the local
    # surface exclusively to the detailed mesh. A coarse triangle must never
    # interpolate over NOV or the camera and bury them on a sharp slope.
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var local_min_x: float = float(maxi(0, cx - 1)) * TILE_M - _layout.half_m
    var local_max_x: float = float(mini(_layout.grid_size, cx + 2)) * TILE_M - _layout.half_m
    var local_min_z: float = float(maxi(0, cz - 1)) * TILE_M - _layout.half_m
    var local_max_z: float = float(mini(_layout.grid_size, cz + 2)) * TILE_M - _layout.half_m
    var xs: Array[float] = [local_min_x, local_max_x]
    var zs: Array[float] = [local_min_z, local_max_z]
    for index in range(HORIZON_GRID + 1):
        xs.append(origin + float(index) * step)
        zs.append(origin + float(index) * step)
    xs.sort()
    zs.sort()
    for z_index in range(zs.size() - 1):
        for x_index in range(xs.size() - 1):
            var x := xs[x_index]
            var z := zs[z_index]
            var nx := xs[x_index + 1]
            var nz := zs[z_index + 1]
            if is_equal_approx(x, nx) or is_equal_approx(z, nz):
                continue
            var mid_x := (x + nx) * 0.5
            var mid_z := (z + nz) * 0.5
            if mid_x > local_min_x and mid_x < local_max_x and mid_z > local_min_z and mid_z < local_max_z:
                continue
            _horizon_vertex(st, x, z)
            _horizon_vertex(st, nx, z)
            _horizon_vertex(st, x, nz)
            _horizon_vertex(st, nx, z)
            _horizon_vertex(st, nx, nz)
            _horizon_vertex(st, x, nz)
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
    if _physical_weather != null and (name.contains("Undergrowth") or name == "MidgroundVegetation"):
        instance.material_override = _physical_weather.grass_material(color,float(mesh.height)*0.5 if mesh is CylinderMesh else 0.7)
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
    var rows: Array = _distant_residency.update(_position, DISTANT_VEGETATION_COUNT,
        1.0, 48.0, DISTANT_VEGETATION_OUTER_M, 430.0, 211,
        _layout.half_m, Callable(self, "_midground_allowed"), DISTANT_VEGETATION_INNER_M)
    var index := 0
    for record in rows:
        if not record.has("trunk"):
            var p: Vector2 = record["point"]
            var noise: float = record["noise"]
            var scale := 0.82 + 0.54 * noise
            var basis := Basis(Vector3.UP, noise * TAU).scaled(Vector3.ONE * scale)
            var y := _height(p.x, p.y)
            record["trunk"] = Transform3D(basis, Vector3(p.x, y + 1.9 * scale, p.y))
            record["canopy"] = Transform3D(basis, Vector3(p.x, y + 5.2 * scale, p.y))
        _distant_trunks.multimesh.set_instance_transform(index, record["trunk"])
        _distant_canopies.multimesh.set_instance_transform(index, record["canopy"])
        index += 1
    _distant_trunks.multimesh.visible_instance_count = index
    _distant_canopies.multimesh.visible_instance_count = index
    preload("res://nature_batch_collision.gd").sync(_distant_trunks, rows.map(func(row): return row["trunk"]), true)

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
    var rows: Array = _midground_residency.update(_position, MIDGROUND_VEGETATION_COUNT,
        1.0, 8.0, MIDGROUND_VEGETATION_OUTER_M, 120.0, 237,
        _layout.half_m, Callable(self, "_midground_allowed"), MIDGROUND_VEGETATION_INNER_M)
    var placed := 0
    for record in rows:
        if not record.has("transform"):
            var p: Vector2 = record["point"]
            var noise: float = record["noise"]
            var scale := 0.55 + 0.65 * noise
            var basis := Basis(Vector3.UP, noise * TAU).scaled(Vector3(scale, scale * (0.82 + 0.28 * noise), scale))
            record["transform"] = Transform3D(basis, Vector3(p.x, _height(p.x, p.y) + 0.67 * scale, p.y))
        _midground_vegetation.multimesh.set_instance_transform(placed, record["transform"])
        placed += 1
    _midground_vegetation.multimesh.visible_instance_count = placed
    preload("res://nature_batch_collision.gd").sync(_midground_vegetation, rows.map(func(row): return row["transform"]))

func _height(x: float, z: float) -> float:
    # Use the exact triangles of the 8 m rendered grid for feet and camera.
    var step := TILE_M / 8.0
    var half_m: float = _layout.half_m if _layout != null else 1024.0
    var x0: float = floor((x + half_m) / step) * step - half_m
    var z0: float = floor((z + half_m) / step) * step - half_m
    var u: float = (x - x0) / step
    var v: float = (z - z0) / step
    var a := _raw_height(x0, z0)
    if is_zero_approx(u) and is_zero_approx(v):
        return a
    if is_zero_approx(u):
        return lerpf(a, _raw_height(x0, z0 + step), v)
    if is_zero_approx(v):
        return lerpf(a, _raw_height(x0 + step, z0), u)
    var b := _raw_height(x0 + step, z0)
    var c := _raw_height(x0, z0 + step)
    if u + v <= 1.0:
        return a + u * (b - a) + v * (c - a)
    var d := _raw_height(x0 + step, z0 + step)
    return d + (1.0 - u) * (c - d) + (1.0 - v) * (b - d)

func _raw_height(x: float, z: float) -> float:
    var key := Vector2(x, z)
    if _consolidated_ground.has(key):
        return float(_consolidated_ground[key])
    return _ground_consolidation.sample(key,_proposed_raw_height(x,z),_consolidated_ground)

func _proposed_raw_height(x: float, z: float) -> float:
    var highland_mix := smoothstep(143.0,207.0,x)*(1.0-smoothstep(-102.0,-38.0,z))
    var rise := lerpf(1.0,4.0,highland_mix)
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
    # Physical ground uses the identical resident triangles. Layer 2 is for
    # wildlife and sight; Nov retains its existing analytical walking floor.
    var physics_ground := StaticBody3D.new()
    physics_ground.name = "ResidentTerrainCollider"
    physics_ground.collision_layer = 2
    physics_ground.collision_mask = 0
    var shape := ConcavePolygonShape3D.new()
    var faces: PackedVector3Array = ground.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].duplicate()
    for i in range(0,faces.size(),3):
        var swap := faces[i+1]
        faces[i+1] = faces[i+2]
        faces[i+2] = swap
    shape.set_faces(faces)
    shape.backface_collision = true
    var collision := CollisionShape3D.new()
    collision.shape = shape
    physics_ground.add_child(collision)
    ground.add_child(physics_ground)
    # Keep the actual rendered vertex heights with the resident tile.
    var heights := PackedFloat32Array()
    heights.resize(81)
    var vertices: PackedVector3Array = ground.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
    for vertex in vertices:
        var ix := clampi(roundi((vertex.x - x0) / step), 0, 8)
        var iz := clampi(roundi((vertex.z - z0) / step), 0, 8)
        heights[iz * 9 + ix] = vertex.y
    ground.set_meta("resident_ground_heights", heights)
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
    if kind == "tree" or kind == "rock" or path.get_file().begins_with("Bush_"):
        preload("res://nature_batch_collision.gd").attach_model(n, kind == "tree")
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
        var parts: PackedStringArray = str(id).split(":")
        var bounds := Rect2(_layout.tile_origin(int(parts[0]), int(parts[1])), Vector2.ONE * _layout.tile_size_m)
        var closest := Vector2(clampf(_position.x, bounds.position.x, bounds.end.x), clampf(_position.z, bounds.position.y, bounds.end.y))
        if closest.distance_to(Vector2(_position.x, _position.z)) <= LOCAL_STABLE_RADIUS_M:
            continue
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
    _last_live_position = projected
    _has_live_position = true
    if not _local_explore_enabled and first_bind:
        _position = projected
        _live_walk_velocity = Vector2.ZERO
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
        if first_bind:
            _follow_camera(true, 0.0, true)
    _update_caption()
    if first_bind:
        print("WORLD_MAP_LIVE_BOUND region=%s sequence=%d cell=%d:%d hot=%d warm=%d regions=%d" % [_live_region_id, _live_sequence, _cell(_position.x), _cell(_position.z), _live_hot_count, _live_warm_count, _live_region_count])
func _on_local_mode(enabled: bool) -> void:
    _local_explore_enabled = enabled
    if not enabled and _has_live_position:
        var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
        _position = _last_live_position
        _live_walk_velocity = Vector2.ZERO
        if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
            _sync_tiles()
            _rebuild_horizon_ground()
            _rebuild_distant_vegetation()
            _rebuild_midground_vegetation()
        _follow_camera()
    elif enabled:
        _local_motion.snap_body(_walker, _position)
    _update_caption()
func _update_camera_heading(previous: Vector3, current: Vector3, delta: float = 1.0 / 60.0) -> void:
    _camera_forward = _camera_stabilizer.observe_motion(previous, current, delta, _camera_forward)

func _orient_nov_visual() -> void:
    if _walker == null or _camera_forward.length_squared() < 0.001:
        return
    _walker.rotation.y = float(_animal_search_selection.get("heading",0.0)) if _animal_search_selection.get("phase","")=="scan" else atan2(_camera_forward.x, _camera_forward.z)
func _follow_camera(snap_body: bool = true, delta: float = 1.0 / 60.0, reset_camera: bool = false) -> void:
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

    _camera_stabilizer.follow(camera_position, target, delta, reset_camera)
    camera_position = _camera_stabilizer.position
    target = _camera_stabilizer.target
    camera_position.y = maxf(camera_position.y,
        _height(camera_position.x, camera_position.z) + CAMERA_MIN_GROUND_CLEARANCE_M)

    _camera_stabilizer.position.y = camera_position.y
    var pivot := _position + Vector3(0.0, CAMERA_LOOK_HEIGHT_M, 0.0)
    var safe_arm := pivot.distance_to(camera_position)
    if is_inside_tree() and get_world_3d() != null:
        var query := PhysicsRayQueryParameters3D.create(pivot, camera_position, 1)
        query.collide_with_areas = false
        query.hit_from_inside = true
        var hit := get_world_3d().direct_space_state.intersect_ray(query)
        if not hit.is_empty():
            var hit_position: Vector3 = hit.get("position", camera_position)
            safe_arm = maxf(0.0,pivot.distance_to(hit_position)-CAMERA_COLLISION_MARGIN_M)
    camera_position = _camera_stabilizer.constrain_arm(pivot,camera_position,safe_arm,delta,reset_camera)
    camera_position.y = maxf(camera_position.y,
        _height(camera_position.x,camera_position.z)+CAMERA_MIN_GROUND_CLEARANCE_M)
    # Keep the nominal follower independent from the collision-constrained eye.
    _camera.position = camera_position
    _camera.look_at(target, Vector3.UP)
func _update_caption() -> void:
    if _hud!=null and _local_motion!=null:
        _hud.set_animal_world(str(_local_motion._episodes.context.get("world_id","")))
        _hud.update_learning(_local_motion._experience,_local_motion._journey)
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    if _live_authoritative and not _local_explore_enabled:
        var feed_state := str(_live_feed.get("connection_state")) if _live_feed != null else "sem feed"
        _hud.update_live(_tiles.size(), MAX_ACTIVE_DECOR, _live_region_id, _live_sequence, feed_state, cx, cz, _biome(cx, cz), _live_hot_count, _live_warm_count, _live_region_count)
    else:
        _hud.update_local(_tiles.size(), MAX_ACTIVE_DECOR, cx, cz, _biome(cx, cz), _local_surface, _local_block_reason, _local_explore_enabled)
func _animate_nov_movement(previous: Vector3, delta: float) -> void:
    var visual := _walker.get_node_or_null("NovVisual")
    if visual == null:
        return
    var velocity := (_position - previous) / maxf(delta, 0.001)
    var heading := atan2(velocity.x, velocity.z) - _walker.rotation.y
    if Vector2(velocity.x, velocity.z).length() < 0.08:
        heading = float(visual.get("_visual_heading"))
    visual.call("set_motion_velocity", velocity, heading)

func _advance_live_walk(delta: float) -> void:
    _local_motion._episodes.enabled = not OS.has_feature("web") and not OS.get_cmdline_user_args().has("--offline-tour")
    _local_motion._experience.working_memory.enabled = _local_motion._episodes.enabled and not _local_motion._experience.working_memory.world_id.is_empty()
    _local_motion._pattern_collector.set_enabled(_local_motion._episodes.enabled)
    var dt := clampf(delta, 0.0, 0.1)
    var world := str(_local_motion._episodes.context.get("world_id", ""))
    var logical_ms := floori(_day_cycle._logical_ms+_day_cycle._elapsed*1000.0)
    _animal_search_selection = {}
    if OS.has_feature("web") and _hud!=null and bool(_day_cycle.sample().get("synced",false)) and not _day_cycle._paused:
        _animal_search_selection = _hud._animal_search.intent(-1.0,logical_ms)
    elif _animal_search_intent.enabled:
        if not bool(_day_cycle.sample().get("synced",false)) or _day_cycle._paused or _day_cycle._world_id!=world:
            _animal_search_intent.suspend("clock_unavailable")
        else:
            _animal_search_intent._approach.context_probe=Callable(_local_motion,"approach_context")
            _animal_search_selection = _animal_search_intent.choose(_position,world,logical_ms,
                not _route_goal.active and _local_motion._journey.closed,Callable(_local_motion,"resolve_destination"),
                _visual_perception.latest(),atan2(_camera_forward.x,_camera_forward.z))
    var search_key := str(_animal_search_selection.get("id",""))+":"+str(_animal_search_selection.get("phase",""))+":"+str(_animal_search_selection.get("revision",0)) if not _animal_search_selection.is_empty() else ""
    if search_key!=_animal_search_route:
        _local_motion._journey.abort("intenção de busca mudou","search_intent_changed")
        _route_goal.reset()
        _animal_search_route=search_key
    var desired_target := _last_live_position
    if not _animal_search_selection.is_empty():
        var point: Array = _animal_search_selection.goal
        desired_target=Vector3(point[0],point[1],point[2])
    var committed_target: Vector3 = _route_goal.choose(_position, desired_target, dt, world, Callable(_local_motion,"resolve_destination"))
    if _route_goal.last_ended_id==_local_motion._journey.identity and not _route_goal.last_ended_reason.is_empty():
        _local_motion._journey.abort("objetivo reavaliado",_route_goal.last_ended_reason)
    if _local_motion.route_goal_id != _route_goal.identity():
        _local_motion._experience.active = false
        _local_motion._experience.reset_route_plan()
    _local_motion.route_goal_id = _route_goal.identity()
    _local_motion._experience.trial_error_enabled = true
    _local_motion.commit_journey(_local_motion.route_goal_id,committed_target,_position)
    var previous := _position
    var current_flat := Vector2(_position.x, _position.z)
    var target_flat := Vector2(committed_target.x, committed_target.z)
    var offset := target_flat - current_flat
    var distance := offset.length()
    var desired := Vector2.ZERO
    if distance <= 0.04:
        # Rejected destinations can leave no committed route. Keep monitoring
        # that failed attempt, while ordinary idle/arrival remains exempt.
        var rejected_latest: bool = _route_goal._rejected_latest.is_finite() and _route_goal._rejected_latest.distance_to(_last_live_position)<0.1
        if not OS.get_cmdline_user_args().has("--offline-tour") and _stuck_recovery.observe(_position,_last_live_position,delta,rejected_latest):
            _attempt_stuck_recovery()
            return
        _live_walk_velocity = Vector2.ZERO
        _local_motion._locomotion.stop()
        _follow_camera(false, dt)
        _animate_nov_movement(previous, dt)
        return
    if distance > 0.04:
        var approach_speed := minf(LIVE_WALK_SPEED_MPS, sqrt(2.0 * LIVE_WALK_ACCEL_MPS2 * distance))
        desired = offset / distance * approach_speed
    _live_walk_velocity = _live_walk_velocity.move_toward(desired, LIVE_WALK_ACCEL_MPS2 * dt)
    var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
    var movement: Dictionary = _local_motion.advance(
        _position, Vector2.ZERO, committed_target, dt, _walker,
        get_world_3d().direct_space_state, true, LIVE_WALK_SPEED_MPS if _local_motion.inertial_enabled else _live_walk_velocity.length()
    )
    _animal_search_intent._approach.observe_movement(movement)
    _position = movement.get("position", _position)
    _local_surface = str(movement.get("surface", "terrain"))
    _local_block_reason = str(movement.get("reason", ""))
    if not OS.get_cmdline_user_args().has("--offline-tour") and _stuck_recovery.observe(_position,committed_target,delta,true):
        _attempt_stuck_recovery()
        return
    if distance < 0.04:
        _live_walk_velocity = Vector2.ZERO
    _update_camera_heading(previous, _position, dt)
    if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
        _sync_tiles()
        _rebuild_horizon_ground()
        _rebuild_distant_vegetation()
        _rebuild_midground_vegetation()
    _perceptual_vegetation.rebuild(_position, _camera_forward, _live_region_id)
    _perceptual_assets.rebuild(_position, _camera_forward, _live_region_id)
    _follow_camera(false, dt)
    _animate_nov_movement(previous, dt)

func _attempt_stuck_recovery() -> void:
    _animal_search_intent.finish("navigation_recovery")
    _animal_search_selection.clear()
    _recovery_pending = true
    var trapped := _position
    # Load actual start-area colliders before accepting the reset destination.
    _position = _recovery_start
    _sync_tiles()
    _perceptual_vegetation.rebuild(_position,_camera_forward,_live_region_id)
    _perceptual_assets.rebuild(_position,_camera_forward,_live_region_id)
    await get_tree().physics_frame
    var space := get_world_3d().direct_space_state
    var recovery: Dictionary = _local_motion.resolve_recovery_start(_recovery_start,space)
    var recovered := false
    if bool(recovery.get("allowed",false)):
        var safe: Vector3 = recovery["position"]
        recovered = _local_motion.recover_to(trapped,safe,_walker,space)
        if recovered:
            _position = safe
            _route_goal.reset()
            _live_walk_velocity = Vector2.ZERO
            _local_block_reason = ""
            _local_surface = "terrain"
    if not recovered:
        _position = trapped
        print("NOV_STUCK_RECOVERY_DEFERRED reason=no_safe_recovery_start")
    _stuck_recovery.reset()
    _sync_tiles()
    _rebuild_horizon_ground()
    _rebuild_distant_vegetation()
    _rebuild_midground_vegetation()
    _perceptual_vegetation.rebuild(_position,_camera_forward,_live_region_id)
    _perceptual_assets.rebuild(_position,_camera_forward,_live_region_id)
    _follow_camera(true,0.0,true)
    _recovery_pending = false

func _process(delta: float) -> void:
    if _day_environment != null and _day_light != null:
        _day_cycle.advance(delta)
        _day_cycle.present(_day_environment, _day_light)
    if _memory_sky != null and _camera != null:
        _memory_sky.update_view(_camera, _day_cycle, delta)
    if _physical_weather != null and _camera != null:
        _physical_weather.update_view(_camera,_day_cycle,delta,_day_environment,_day_light)
    _poll_native_fps_governor()
    if _recovery_pending:
        return
    if _route.size() < 2:
        return
    if _live_authoritative and not _local_explore_enabled:
        var connected := _live_feed != null and str(_live_feed.get("connection_state")) == "conectado"
        if connected or Time.get_ticks_msec() - _live_last_update_ms < LIVE_STALE_MS:
            _advance_live_walk(delta)
            _clock += delta
            if _clock > 0.5:
                _clock = 0.0
                _update_caption()
            return
        _local_motion._journey.abort("servidor indisponível","feed_unavailable")
        _animal_search_intent.suspend("feed_unavailable")
        _animal_search_selection.clear()
        _live_authoritative = false
        _route_goal.reset()
        _live_region_id = ""
        _live_visual.clear_markers()
    _local_motion._episodes.enabled = false
    _local_motion._episodes.active = {}
    _local_motion._experience.working_memory.enabled = false
    var input := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
    var target := _waypoint(_route[_leg])
    var movement: Dictionary = _local_motion.advance(
        _position, input, target, delta, _walker, get_world_3d().direct_space_state,
        not _local_explore_enabled
    )
    var previous_position := _position
    _animal_search_intent._approach.observe_movement(movement)
    _position = movement.get("position", _position)
    _update_camera_heading(previous_position, _position, delta)
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
    _follow_camera(false, delta)
    _animate_nov_movement(previous_position, delta)
    _clock += delta
    if _clock > 0.3:
        _clock = 0.0
        _update_caption()


func register_perception_target(node: Node3D, identity: String, kind: String, world: String, aim_offset: Vector3 = Vector3(0,0.6,0)) -> bool:
    return _visual_perception.register_target(node,identity,kind,world,aim_offset)

func _physics_process(delta: float) -> void:
    if _walker == null or _local_motion == null or _recovery_pending or not _live_authoritative or Time.get_ticks_msec()-_live_last_update_ms>LIVE_STALE_MS:
        _visual_perception.clear_observation()
        return
    if _wildlife != null:
        _wildlife.update(_day_cycle,_walker,_visual_perception,get_world_3d().direct_space_state,
            str(_local_motion._episodes.context.get("world_id","")),true)
    _perception_elapsed += clampf(delta,0,0.25)
    if _perception_elapsed < 0.25:
        return
    _perception_elapsed = 0.0
    var clock: Dictionary = _day_cycle.sample()
    var world := str(_local_motion._episodes.context.get("world_id",""))
    if not bool(clock.get("synced",false)) or world.is_empty() or world != _day_cycle._world_id:
        _visual_perception.clear_observation()
        return
    var logical_ms := floori(float(_day_cycle._logical_ms)+float(_day_cycle._elapsed)*1000.0)
    var observation: Dictionary = _visual_perception.scan(_walker,_walker.global_basis.z,get_world_3d().direct_space_state,
        world,logical_ms,float(clock.get("daylight",1.0)))
    if not observation.is_empty() and not _perception_announced:
        _perception_announced = true
        print("NOV_VISUAL_PERCEPTION_ACTIVE world=%s day_range_m=24 night_range_m=12 fov_deg=120 occlusion=physical_eye_ray" % world)

func _exit_tree() -> void:
    if _local_motion!=null and _local_motion.has_method("abort_journey"):
        _local_motion.abort_journey("renderizador encerrado","renderer_shutdown")
