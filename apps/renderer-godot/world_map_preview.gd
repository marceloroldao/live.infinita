extends Node3D
# Visual tour with an optional read-only spatial feed; never mutates World State.
const Catalog = preload("res://nature_asset_catalog.gd")
const Features = preload("res://world_map_features.gd")
const LiveVisual = preload("res://world_map_live_visual.gd")
const MAP_PATH := "res://world_map_001.json"
const TILE_M := 64.0
const GRID := 16
const HALF := GRID * TILE_M * 0.5
const ACTIVE_RADIUS := 1
const DECOR_PER_TILE := 6
const MAX_ACTIVE_TILES := 9
const MAX_ACTIVE_DECOR := 54
const LIVE_STALE_MS := 10000
const TOUR_SPEED_MPS := 13.0

var _map: Dictionary = {}
var _catalog: RefCounted
var _features: RefCounted
var _tiles: Dictionary = {}
var _resource_cache: Dictionary = {}
var _walker: MeshInstance3D
var _camera: Camera3D
var _status: Label
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
var _live_visual: RefCounted

func _ready() -> void:
    var data = JSON.parse_string(FileAccess.get_file_as_string(MAP_PATH))
    if typeof(data) != TYPE_DICTIONARY or str(data.get("schema", "")) != "live-infinita-visual-world-map/v1":
        push_error("WORLD_MAP_PREVIEW_BAD_MANIFEST")
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
    _features = Features.new(Callable(self, "_height"))
    _live_visual = LiveVisual.new(self, _features, _map)
    _position = _waypoint(_route[0])
    for argument in OS.get_cmdline_user_args():
        if str(argument).begins_with("--preview-cell="):
            var parts := str(argument).trim_prefix("--preview-cell=").split(",")
            if parts.size() == 2 and parts[0].is_valid_int() and parts[1].is_valid_int():
                var x := parts[0].to_int()
                var z := parts[1].to_int()
                if x >= 0 and x < GRID and z >= 0 and z < GRID:
                    _position = _waypoint([x, z])
    _build_stage()
    _sync_tiles()
    _update_caption()
    print("WORLD_MAP_PREVIEW_READY grid=16x16 meters=1024 active_tiles=%d decor_budget=%d" % [_tiles.size(), MAX_ACTIVE_DECOR])

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
    _live_visual.build()
    _camera = Camera3D.new()
    _camera.current = true
    _camera.far = 280.0
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
    var bank_mix := clampf((absf(x - 32.0) - 10.0) / 20.0, 0.0, 1.0)
    return lerpf(minf(natural, -2.3), natural, bank_mix)

func _waypoint(cell: Array) -> Vector3:
    var x := (float(cell[0]) + 0.5) * TILE_M - HALF
    var z := (float(cell[1]) + 0.5) * TILE_M - HALF
    return Vector3(x, float(_features.call("walk_height", x, z)), z)

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
    var kind := "tree" if index < 3 and biome != "village" else ("rock" if index % 2 == 0 else "plant")
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

func _sync_tiles() -> void:
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    var wanted := {}
    for z in range(maxi(0, cz - ACTIVE_RADIUS), mini(GRID, cz + ACTIVE_RADIUS + 1)):
        for x in range(maxi(0, cx - ACTIVE_RADIUS), mini(GRID, cx + ACTIVE_RADIUS + 1)):
            var id := "%d:%d" % [x, z]
            wanted[id] = true
            if _tiles.has(id):
                continue
            var tile := Node3D.new()
            tile.name = "Tile_%d_%d" % [x, z]
            add_child(tile)
            var biome := _biome(x, z)
            tile.add_child(_terrain(x, z, biome))
            var features: Array[String] = _features.decorate(tile, x, z, biome, _map.get("landmarks", []), _route)
            print("WORLD_MAP_TILE_READY cell=%s biome=%s features=%s" % [id, biome, ",".join(features)])
            for i in range(DECOR_PER_TILE):
                _decoration(tile, x, z, i, biome)
            _tiles[id] = tile
    for id in _tiles.keys().duplicate():
        if not wanted.has(id):
            var stale: Node3D = _tiles[id]
            _tiles.erase(id)
            stale.queue_free()
    assert(_tiles.size() <= MAX_ACTIVE_TILES)

func _on_world_slice(observer: Dictionary, current_region_id: String, hot_entities: Array, warm_entities: Array, sequence: int) -> void:
    if observer.is_empty():
        return
    var first_bind := not _live_authoritative
    var old_cell := Vector2i(_cell(_position.x), _cell(_position.z))
    _position = _live_visual.project_position(observer)
    _live_authoritative = true
    _live_last_update_ms = Time.get_ticks_msec()
    _live_region_id = current_region_id
    _live_sequence = sequence
    var counts: Dictionary = _live_visual.update_markers(hot_entities, warm_entities)
    _live_hot_count = int(counts.get("hot", 0))
    _live_warm_count = int(counts.get("warm", 0))
    if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
        _sync_tiles()
    _follow_camera()
    _update_caption()
    if first_bind:
        print("WORLD_MAP_LIVE_BOUND region=%s sequence=%d cell=%d:%d hot=%d warm=%d" % [_live_region_id, _live_sequence, _cell(_position.x), _cell(_position.z), _live_hot_count, _live_warm_count])

func _follow_camera() -> void:
    _walker.position = _position + Vector3(0, 1.1, 0)
    _camera.position = _position + Vector3(26, 32, 39)
    _camera.look_at(_position + Vector3(0, 1.0, 0))

func _update_caption() -> void:
    var cx := _cell(_position.x)
    var cz := _cell(_position.z)
    if _live_authoritative:
        var feed_state := str(_live_feed.get("connection_state")) if _live_feed != null else "sem feed"
        _status.text = "LIVE INFINITA / VALE DE NOV\n1.024 x 1.024 m | %d setores ativos | max %d decoracoes\nNOV autoritativo | regiao %s | seq %d | %s\nSetor %d,%d - %s | HOT %d / WARM %d | somente leitura" % [_tiles.size(), MAX_ACTIVE_DECOR, _live_region_id, _live_sequence, feed_state, cx, cz, _biome(cx, cz), _live_hot_count, _live_warm_count]
    else:
        _status.text = "LIVE INFINITA / VALE DE NOV\n1.024 x 1.024 m | %d setores ativos | max %d decoracoes\nSetor %d,%d - %s | percurso visual offline\nSetas: explorar manualmente" % [_tiles.size(), MAX_ACTIVE_DECOR, cx, cz, _biome(cx, cz)]

func _process(delta: float) -> void:
    if _route.size() < 2:
        return
    if _live_authoritative:
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
    if input.length_squared() > 0.01:
        _position.x = clampf(_position.x + input.x * TOUR_SPEED_MPS * delta, -HALF + 1.0, HALF - 1.0)
        _position.z = clampf(_position.z + input.y * TOUR_SPEED_MPS * delta, -HALF + 1.0, HALF - 1.0)
    else:
        var target := _waypoint(_route[_leg])
        var flat := Vector2(_position.x, _position.z).move_toward(Vector2(target.x, target.z), TOUR_SPEED_MPS * delta)
        _position.x = flat.x
        _position.z = flat.y
        if flat.distance_to(Vector2(target.x, target.z)) < 0.1:
            _leg = (_leg + 1) % _route.size()
    _position.y = float(_features.call("walk_height", _position.x, _position.z))
    if old_cell != Vector2i(_cell(_position.x), _cell(_position.z)):
        _sync_tiles()
    _follow_camera()
    _clock += delta
    if _clock > 0.3:
        _clock = 0.0
        _update_caption()
