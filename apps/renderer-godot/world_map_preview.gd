extends Node3D
# Isolated 3D preview. Optional one-way Nov observer; never writes World State.
const Catalog = preload("res://nature_asset_catalog.gd")
const Features = preload("res://world_map_features.gd")
const ProxyFoliage = preload("res://world_map_proxy_foliage.gd")
const NovFollow = preload("res://nov_map_follow.gd")
const NOV_PROJECTION_PATH := "res://nov_map_projection_001.json"
const MAP_PATH := "res://world_map_001.json"
const TILE_M := 64.0
const GRID := 16
const HALF := GRID * TILE_M * 0.5
const ACTIVE_RADIUS := 1
const DECOR_PER_TILE := 3
const LOW_SPEC_DECOR_PER_TILE := 1
const MAX_ACTIVE_TILES := 9
const MAX_ACTIVE_DECOR := 27
const MAX_LOW_SPEC_PROXIES := 45
const DETAIL_LAYER_NAME := "DetailedDecor"
const STREAM_TILES_PER_FRAME := 1
const TOUR_SPEED_MPS := 13.0

var _map: Dictionary = {}
var _catalog: RefCounted
var _features: RefCounted
var _proxy_foliage: RefCounted
var _route_points: Array = []
var _tiles: Dictionary = {}
var _pending_add: Array[Vector2i] = []
var _pending_remove: Array[String] = []
var _focus_cell := Vector2i(-1, -1)
var _resource_cache: Dictionary = {}
var _walker: MeshInstance3D
var _camera: Camera3D
var _status: Label
var _route: Array = []
var _leg := 1
var _position := Vector3.ZERO
var _clock := 0.0
var _follow_nov := false
var _has_follow_pose := false
var _nov_follow: RefCounted
var _follow_status := "desligado"
var _follow_region := ""
var _follow_sequence := -1
var _benchmark_seconds := 0.0
var _benchmark_elapsed := 0.0
var _benchmark_frames := 0
var _benchmark_max_delta := 0.0
var _benchmark_target_fps := 0
var _server_low_spec := false

func _ready() -> void:
    var data = JSON.parse_string(FileAccess.get_file_as_string(MAP_PATH))
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != "live-infinita-visual-world-map/v1":
        push_error("WORLD_MAP_PREVIEW_BAD_MANIFEST")
        return
    _map = data
    _route = _map.get("route", [])
    if _route.size() < 2:
        push_error("WORLD_MAP_PREVIEW_NO_ROUTE")
        return
    _catalog = Catalog.new()
    _features = Features.new()
    _proxy_foliage = ProxyFoliage.new()
    for waypoint in _route:
        _route_points.append(_waypoint(waypoint))
    _position = _waypoint(_route[0])
    for argument in OS.get_cmdline_user_args():
        if str(argument) == "--follow-nov":
            _follow_nov = true
        if str(argument) == "--server-low-spec":
            _server_low_spec = true
        if str(argument).begins_with("--benchmark-seconds="):
            var raw_seconds := str(argument).trim_prefix("--benchmark-seconds=")
            if raw_seconds.is_valid_float():
                _benchmark_seconds = clampf(raw_seconds.to_float(), 0.0, 60.0)
        if str(argument).begins_with("--benchmark-fps="):
            var raw_fps := str(argument).trim_prefix("--benchmark-fps=")
            if raw_fps.is_valid_int():
                _benchmark_target_fps = clampi(raw_fps.to_int(), 1, 60)
        if str(argument).begins_with("--preview-cell="):
            var pieces := str(argument).trim_prefix("--preview-cell=").split(",")
            if pieces.size() == 2 and pieces[0].is_valid_int() and pieces[1].is_valid_int():
                var px := pieces[0].to_int()
                var pz := pieces[1].to_int()
                if px >= 0 and px < GRID and pz >= 0 and pz < GRID:
                    _position = _waypoint([px, pz])
    if _benchmark_target_fps > 0:
        Engine.max_fps = _benchmark_target_fps
    if _follow_nov:
        _start_nov_follow()
    _build_stage()
    _sync_tiles()
    _update_caption()
    var proxy_budget := MAX_LOW_SPEC_PROXIES if _server_low_spec else 0
    print("WORLD_MAP_PREVIEW_READY grid=16x16 meters=1024 active_tiles=%d detailed_budget=%d proxy_budget=%d low_spec=%s" % [_tiles.size(), _detailed_budget(), proxy_budget, str(_server_low_spec)])

func _nov_socket_url() -> String:
    if OS.has_feature("web"):
        var scheme := "wss://" if str(JavaScriptBridge.eval("window.location.protocol")) == "https:" else "ws://"
        return scheme + str(JavaScriptBridge.eval("window.location.host")) + "/ws"
    return "ws://127.0.0.1:8080/ws"

func _start_nov_follow() -> void:
    var data = JSON.parse_string(FileAccess.get_file_as_string(NOV_PROJECTION_PATH))
    if typeof(data) != TYPE_DICTIONARY:
        _follow_status = "mapping_indisponivel"
        return
    _nov_follow = NovFollow.new(data)
    _nov_follow.start(_nov_socket_url())
    _follow_status = "aguardando_nov"
    print("NOV_MAP_FOLLOW_READ_ONLY_ENABLED")

func _tick_nov_follow(delta: float) -> void:
    if _nov_follow == null:
        return
    var value: Dictionary = _nov_follow.poll()
    _follow_status = str(value.get("status", "sem_dados"))
    if value.get("fresh") != true or value.get("has_pose") != true:
        return
    var target: Vector2 = value["position"]
    if not _has_follow_pose:
        _position.x = target.x
        _position.z = target.y
        _has_follow_pose = true
    else:
        var alpha := 1.0 - exp(-delta * 3.0)
        _position.x = lerpf(_position.x, target.x, alpha)
        _position.z = lerpf(_position.z, target.y, alpha)
    _follow_region = str(value["region_id"])
    if _follow_sequence != int(value["sequence"]):
        _follow_sequence = int(value["sequence"])
        print("NOV_MAP_FOLLOW_ACCEPTED seq=%d region=%s" % [_follow_sequence, _follow_region])

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
    atmosphere.environment = env
    add_child(atmosphere)
    _walker = MeshInstance3D.new()
    _walker.name = "NovVisualMarker"
    var capsule := CapsuleMesh.new()
    capsule.radius = 0.48
    capsule.height = 1.8
    _walker.mesh = capsule
    _walker.material_override = _material(Color("#eeb74b"))
    add_child(_walker)
    _camera = Camera3D.new()
    _camera.current = true
    _camera.far = 190.0
    add_child(_camera)
    var overlay := CanvasLayer.new()
    add_child(overlay)
    _status = Label.new()
    _status.position = Vector2(18, 22)
    _status.add_theme_color_override("font_color", Color.WHITE)
    _status.add_theme_color_override("font_shadow_color", Color.BLACK)
    _status.add_theme_constant_override("shadow_offset_x", 2)
    _status.add_theme_constant_override("shadow_offset_y", 2)
    overlay.add_child(_status)
    _follow_camera()

func _material(color: Color) -> StandardMaterial3D:
    var result := StandardMaterial3D.new()
    result.albedo_color = color
    result.roughness = 1.0
    return result

func _height(x: float, z: float) -> float:
    var rise := 4.0 if x > 175.0 and z < -70.0 else 1.0
    var natural := (sin(x * 0.012) * 1.8 + cos(z * 0.016) * 1.6 + sin((x + z) * 0.021) * 0.9) * rise
    var shore := clampf((absf(x - 32.0) - 10.0) / 20.0, 0.0, 1.0)
    return lerpf(minf(natural, -3.25), natural, shore)

func _walk_height(x: float, z: float) -> float:
    var base := _height(x, z)
    if absf(z + 32.0) > 2.4 or x < 7.0 or x > 57.0:
        return base
    var deck_mix := clampf(minf(x - 7.0, 57.0 - x) / 5.0, 0.0, 1.0)
    return lerpf(base, 3.62, deck_mix)

func _waypoint(cell: Array) -> Vector3:
    var x := (float(cell[0]) + 0.5) * TILE_M - HALF
    var z := (float(cell[1]) + 0.5) * TILE_M - HALF
    return Vector3(x, _walk_height(x, z), z)

func _cell(value: float) -> int:
    return clampi(floori((value + HALF) / TILE_M), 0, GRID - 1)

func _biome(cx: int, cz: int) -> String:
    if cx == 8: return "river"
    if abs(cx - 11) <= 1 and abs(cz - 9) <= 1: return "village"
    if cx >= 11 and cz <= 5: return "hills"
    if abs(cx - 5) <= 1 and abs(cz - 7) <= 1: return "clearing"
    return "forest"

func _terrain_color(biome: String) -> Color:
    match biome:
        "river": return Color("#397eaa")
        "village": return Color("#987e5a")
        "hills": return Color("#8a9c6b")
        "clearing": return Color("#80a56b")
        _: return Color("#52784e")

func _vertex(st: SurfaceTool, x: float, z: float) -> void:
    st.add_vertex(Vector3(x, _height(x, z), z))

func _terrain(cx: int, cz: int, biome: String) -> MeshInstance3D:
    var st := SurfaceTool.new()
    st.begin(Mesh.PRIMITIVE_TRIANGLES)
    var x0 := float(cx) * TILE_M - HALF
    var z0 := float(cz) * TILE_M - HALF
    var step := TILE_M / 8.0
    for j in range(8):
        for i in range(8):
            var x := x0 + i * step
            var z := z0 + j * step
            _vertex(st, x, z)
            _vertex(st, x, z + step)
            _vertex(st, x + step, z)
            _vertex(st, x + step, z)
            _vertex(st, x, z + step)
            _vertex(st, x + step, z + step)
    st.generate_normals()
    var ground := MeshInstance3D.new()
    ground.mesh = st.commit()
    ground.material_override = _material(_terrain_color(biome))
    return ground

func _decoration(parent: Node3D, cx: int, cz: int, index: int, biome: String) -> void:
    if biome == "river":
        return
    var kind := "tree" if index < 2 and biome != "village" else ("rock" if index % 2 == 0 else "plant")
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
    var a := float(cx * 79 + cz * 131 + index * 47)
    var x := float(cx) * TILE_M - HALF + 6.0 + fposmod(sin(a) * 9843.0, 52.0)
    var z := float(cz) * TILE_M - HALF + 6.0 + fposmod(sin(a * 1.37) * 5347.0, 52.0)
    var n: Node3D = model
    n.position = Vector3(x, _height(x, z), z)
    n.scale = Vector3.ONE * (0.75 if kind == "tree" else 0.90)
    parent.add_child(n)

func _wanted_cells(cx: int, cz: int) -> Array[Vector2i]:
    var center := Vector2i(cx, cz)
    var cells: Array[Vector2i] = [center]
    for z in range(maxi(0, cz - ACTIVE_RADIUS), mini(GRID, cz + ACTIVE_RADIUS + 1)):
        for x in range(maxi(0, cx - ACTIVE_RADIUS), mini(GRID, cx + ACTIVE_RADIUS + 1)):
            var cell := Vector2i(x, z)
            if cell != center:
                cells.append(cell)
    return cells

func _detailed_budget() -> int:
    return LOW_SPEC_DECOR_PER_TILE if _server_low_spec else MAX_ACTIVE_DECOR

func _detail_count_for(cell: Vector2i) -> int:
    if _server_low_spec:
        return LOW_SPEC_DECOR_PER_TILE if cell == _focus_cell else 0
    return DECOR_PER_TILE

func _apply_detail_to_tile(cell: Vector2i, tile: Node3D) -> void:
    var old_layer := tile.get_node_or_null(DETAIL_LAYER_NAME)
    if old_layer != null:
        tile.remove_child(old_layer)
        old_layer.queue_free()
    var count := _detail_count_for(cell)
    if count <= 0:
        return
    var layer := Node3D.new()
    layer.name = DETAIL_LAYER_NAME
    tile.add_child(layer)
    for index in range(count):
        _decoration(layer, cell.x, cell.y, index, _biome(cell.x, cell.y))

func _refresh_focus_detail(previous: Vector2i, current: Vector2i) -> void:
    if not _server_low_spec or previous == current:
        return
    for cell in [previous, current]:
        if cell.x < 0 or cell.y < 0:
            continue
        var id := "%d:%d" % [cell.x, cell.y]
        if _tiles.has(id):
            _apply_detail_to_tile(cell, _tiles[id])

func _build_tile(cell: Vector2i) -> void:
    var x := cell.x
    var z := cell.y
    var id := "%d:%d" % [x, z]
    if _tiles.has(id):
        return
    var tile := Node3D.new()
    tile.name = "Tile_%d_%d" % [x, z]
    add_child(tile)
    var biome := _biome(x, z)
    tile.add_child(_terrain(x, z, biome))
    _features.add_to_tile(tile, x, z, biome, _route_points, Callable(self, "_height"), Callable(self, "_walk_height"))
    var proxies := 0
    if _server_low_spec:
        proxies = _proxy_foliage.add_to_tile(tile, x, z, biome, Callable(self, "_height"))
    _apply_detail_to_tile(cell, tile)
    print("WORLD_MAP_TILE_READY cell=%s biome=%s proxies=%d details=%d" % [id, biome, proxies, _detail_count_for(cell)])
    _tiles[id] = tile

func _sync_tiles() -> void:
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var previous_focus := _focus_cell
    _focus_cell = Vector2i(cx, cz)
    _refresh_focus_detail(previous_focus, _focus_cell)
    var cells := _wanted_cells(cx, cz)
    var wanted := {}
    for cell in cells:
        wanted["%d:%d" % [cell.x, cell.y]] = true
    if _tiles.is_empty():
        for cell in cells:
            _build_tile(cell)
        assert(_tiles.size() <= MAX_ACTIVE_TILES)
        return
    _pending_add.clear()
    _pending_remove.clear()
    for cell in cells:
        var id := "%d:%d" % [cell.x, cell.y]
        if not _tiles.has(id):
            _pending_add.append(cell)
    for existing_id in _tiles.keys():
        var id := str(existing_id)
        if not wanted.has(id):
            _pending_remove.append(id)

func _stream_tiles() -> void:
    for _step in range(STREAM_TILES_PER_FRAME):
        if not _pending_remove.is_empty():
            var id: String = _pending_remove[0]
            _pending_remove.remove_at(0)
            if _tiles.has(id):
                var stale: Node3D = _tiles[id]
                _tiles.erase(id)
                stale.queue_free()
        if not _pending_add.is_empty() and _tiles.size() < MAX_ACTIVE_TILES:
            var next_cell: Vector2i = _pending_add[0]
            _pending_add.remove_at(0)
            _build_tile(next_cell)
    assert(_tiles.size() <= MAX_ACTIVE_TILES)

func _follow_camera() -> void:
    _walker.position = _position + Vector3(0, 1.1, 0)
    _camera.position = _position + Vector3(26, 32, 39)
    _camera.look_at(_position + Vector3(0, 1.0, 0))

func _update_caption() -> void:
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var mode := ("Nov real / leitura: %s / %s / seq %d" % [_follow_status, _follow_region, _follow_sequence]) if _follow_nov else "Percurso demonstrativo / setas: explorar"
    var profile := "server-low-spec" if _server_low_spec else "default"
    _status.text = "LIVE INFINITA / VALE DE NOV\n1.024 x 1.024 m | %d setores | %d detalhes | %s\nSetor %d,%d - %s\n%s" % [_tiles.size(), _detailed_budget(), profile, cx, cz, _biome(cx, cz), mode]

func _process(delta: float) -> void:
    if _route.size() < 2:
        return
    var input := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
    if _follow_nov:
        _tick_nov_follow(delta)
    elif input.length_squared() > 0.01:
        _position.x = clampf(_position.x + input.x * TOUR_SPEED_MPS * delta, -HALF + 1.0, HALF - 1.0)
        _position.z = clampf(_position.z + input.y * TOUR_SPEED_MPS * delta, -HALF + 1.0, HALF - 1.0)
    else:
        var target := _waypoint(_route[_leg])
        var flat := Vector2(_position.x, _position.z).move_toward(Vector2(target.x, target.z), TOUR_SPEED_MPS * delta)
        _position.x = flat.x
        _position.z = flat.y
        if flat.distance_to(Vector2(target.x, target.z)) < 0.1:
            _leg = (_leg + 1) % _route.size()
    _position.y = _walk_height(_position.x, _position.z)
    if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
        _sync_tiles()
    _stream_tiles()
    _follow_camera()
    _clock += delta
    if _clock > 0.3:
        _clock = 0.0
        _update_caption()
    if _benchmark_seconds > 0.0:
        _benchmark_elapsed += delta
        _benchmark_frames += 1
        _benchmark_max_delta = maxf(_benchmark_max_delta, delta)
        if _benchmark_elapsed >= _benchmark_seconds:
            var average_fps := float(_benchmark_frames) / maxf(_benchmark_elapsed, 0.001)
            print("WORLD_MAP_BENCHMARK_RESULT seconds=%.3f frames=%d fps=%.2f max_delta_ms=%.2f tiles=%d follow_nov=%s region=%s target_fps=%d" % [
                _benchmark_elapsed, _benchmark_frames, average_fps, _benchmark_max_delta * 1000.0,
                _tiles.size(), str(_follow_nov), _follow_region, _benchmark_target_fps])
            print("WORLD_MAP_BENCHMARK_PROFILE low_spec=%s detailed_budget=%d proxy_budget=%d" % [str(_server_low_spec), _detailed_budget(), MAX_LOW_SPEC_PROXIES if _server_low_spec else 0])
            get_tree().quit()
