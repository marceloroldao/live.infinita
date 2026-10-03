extends RefCounted
# 008BM: a bounded layer of real low-poly nature assets near NOV.
# EnvironmentalState chooses what can appear. This module is presentation-only.

const ASSET_BASE := "res://assets/quaternius/stylized_nature_megakit/models/glTF/"
const COMMON_TREE := ASSET_BASE + "CommonTree_1.gltf"
const PINE_TREE := ASSET_BASE + "Pine_1.gltf"
const COMMON_TREE_MID := ASSET_BASE + "CommonTree_5.gltf"
const PINE_TREE_MID := ASSET_BASE + "Pine_5.gltf"
const BUSH := ASSET_BASE + "Bush_Common.gltf"
const TALL_GRASS := ASSET_BASE + "Grass_Common_Tall.gltf"
const ROCK := ASSET_BASE + "Rock_Medium_1.gltf"

const TREE_BUDGET := 14
const MID_TREE_BUDGET := 18
const UNDERSTORY_BUDGET := 40
const ROCK_BUDGET := 18
const MID_TREE_INNER_M := 30.0
const MID_TREE_OUTER_M := 58.0
const INNER_M := 6.5
const OUTER_M := 31.0
const HALF_ANGLE_RAD := 1.22
const REBUILD_DISTANCE_M := 9.0
const REBUILD_DOT := 0.94
const CORRIDOR_LENGTH_M := 28.0
const CORRIDOR_TREE_ROCK_HALF_WIDTH_M := 3.8
const CORRIDOR_UNDERSTORY_HALF_WIDTH_M := 1.9

var _root: Node3D
var _height_sampler: Callable
var _allowed_sampler: Callable
var _cell_sampler: Callable
var _half_m: float

var _tree_batch: MultiMeshInstance3D
var _mid_tree_batch: MultiMeshInstance3D
var _understory_batch: MultiMeshInstance3D
var _rock_batch: MultiMeshInstance3D

var _environment_by_region: Dictionary = {}
var _environment_state_id := ""
var _last_region_id := ""
var _last_origin := Vector3(999999.0, 0.0, 999999.0)
var _last_forward := Vector3.ZERO
var _mesh_cache: Dictionary = {}
var _current_tree_asset := ""
var _current_mid_tree_asset := ""
var _current_understory_asset := ""
var _vendor_ready := false
var _last_logged_signature := ""

func _init(
    root: Node3D,
    height_sampler: Callable,
    allowed_sampler: Callable,
    cell_sampler: Callable,
    half_m: float,
) -> void:
    _root = root
    _height_sampler = height_sampler
    _allowed_sampler = allowed_sampler
    _cell_sampler = cell_sampler
    _half_m = half_m

func _import_cache_ready(path: String) -> bool:
    var import_path := path + ".import"
    if not FileAccess.file_exists(import_path):
        return false
    var config := ConfigFile.new()
    if config.load(import_path) != OK:
        return false
    var remap_path := str(config.get_value("remap", "path", ""))
    return not remap_path.is_empty() and FileAccess.file_exists(remap_path)

func _first_mesh(node: Node) -> Mesh:
    if node is MeshInstance3D:
        var mesh := (node as MeshInstance3D).mesh
        if mesh != null:
            return mesh
    for child in node.get_children():
        var result := _first_mesh(child)
        if result != null:
            return result
    return null

func _asset_mesh(path: String) -> Mesh:
    if _mesh_cache.has(path):
        return _mesh_cache[path]
    if not _import_cache_ready(path) or not ResourceLoader.exists(path):
        return null
    var packed = load(path)
    if not (packed is PackedScene):
        return null
    var instance = packed.instantiate()
    var mesh := _first_mesh(instance)
    instance.free()
    if mesh != null:
        _mesh_cache[path] = mesh
    return mesh

func _fallback_mesh(kind: String) -> Mesh:
    if kind == "tree":
        var tree := CylinderMesh.new()
        tree.top_radius = 0.3
        tree.bottom_radius = 1.8
        tree.height = 5.0
        tree.radial_segments = 5
        tree.rings = 1
        return tree
    if kind == "rock":
        var rock := BoxMesh.new()
        rock.size = Vector3(1.5, 1.0, 1.2)
        return rock
    var plant := CylinderMesh.new()
    plant.top_radius = 0.08
    plant.bottom_radius = 0.35
    plant.height = 0.9
    plant.radial_segments = 4
    plant.rings = 1
    return plant

func _batch(name: String, mesh: Mesh, budget: int) -> MultiMeshInstance3D:
    var multimesh := MultiMesh.new()
    multimesh.transform_format = MultiMesh.TRANSFORM_3D
    multimesh.mesh = mesh
    multimesh.instance_count = budget
    multimesh.visible_instance_count = 0
    var instance := MultiMeshInstance3D.new()
    instance.name = name
    instance.multimesh = multimesh
    _root.add_child(instance)
    return instance

func build() -> void:
    _vendor_ready = (
        _import_cache_ready(COMMON_TREE)
        and _import_cache_ready(PINE_TREE)
        and _import_cache_ready(COMMON_TREE_MID)
        and _import_cache_ready(PINE_TREE_MID)
        and _import_cache_ready(BUSH)
        and _import_cache_ready(TALL_GRASS)
        and _import_cache_ready(ROCK)
    )
    _tree_batch = _batch("HeroNatureTrees", _fallback_mesh("tree"), TREE_BUDGET)
    _mid_tree_batch = _batch(
        "MidNatureTrees", _fallback_mesh("tree"), MID_TREE_BUDGET
    )
    _understory_batch = _batch(
        "HeroNatureUnderstory", _fallback_mesh("plant"), UNDERSTORY_BUDGET
    )
    _rock_batch = _batch("HeroNatureRocks", _fallback_mesh("rock"), ROCK_BUDGET)
    if _vendor_ready:
        var rock_mesh := _asset_mesh(ROCK)
        if rock_mesh != null:
            _rock_batch.multimesh.mesh = rock_mesh

func vendor_ready() -> bool:
    return _vendor_ready

func update_environment(state: Dictionary) -> bool:
    var next_id := str(state.get("state_id", ""))
    if next_id == _environment_state_id and not next_id.is_empty():
        return false
    var next_map: Dictionary = {}
    var rows = state.get("regions", [])
    if typeof(rows) == TYPE_ARRAY:
        for item in rows:
            if typeof(item) != TYPE_DICTIONARY:
                continue
            var row: Dictionary = item
            var region_id := str(row.get("region_id", ""))
            if not region_id.is_empty():
                next_map[region_id] = row.duplicate(true)
    _environment_state_id = next_id
    _environment_by_region = next_map
    return true

func _environment(region_id: String) -> Dictionary:
    var value = _environment_by_region.get(region_id, {})
    return value if typeof(value) == TYPE_DICTIONARY else {}

func _tree_asset(environment: Dictionary) -> String:
    var climate := str(environment.get("climate_type", "temperate_humid"))
    var zone := str(environment.get("ecological_zone", "sparse"))
    if climate in ["cool_montane", "alpine_cold"] or zone == "alpine_meadow":
        return PINE_TREE
    return COMMON_TREE

func _mid_tree_asset(environment: Dictionary) -> String:
    var climate := str(environment.get("climate_type", "temperate_humid"))
    var zone := str(environment.get("ecological_zone", "sparse"))
    if climate in ["cool_montane", "alpine_cold"] or zone == "alpine_meadow":
        return PINE_TREE_MID
    return COMMON_TREE_MID

func _understory_asset(environment: Dictionary) -> String:
    var zone := str(environment.get("ecological_zone", "sparse"))
    if zone in ["meadow", "wetland", "alpine_meadow"]:
        return TALL_GRASS
    return BUSH

func _environment_factors(environment: Dictionary) -> Vector3:
    if environment.is_empty():
        return Vector3.ZERO
    var vegetation := clampf(float(environment.get("vegetation_density", 0.0)), 0.0, 1.0)
    var tree := clampf(float(environment.get("tree_suitability", 0.0)), 0.0, 1.0)
    var rock := clampf(float(environment.get("rock_exposure", 0.0)), 0.0, 1.0)
    var snow := clampf(float(environment.get("snow_cover", 0.0)), 0.0, 1.0)
    var zone := str(environment.get("ecological_zone", "sparse"))

    var tree_zone := 0.18
    match zone:
        "forest":
            tree_zone = 1.0
        "wetland":
            tree_zone = 0.55
        "meadow":
            tree_zone = 0.28
        "shrubland":
            tree_zone = 0.12
        "alpine_meadow":
            tree_zone = 0.08
        "alpine_rock", "snowfield":
            tree_zone = 0.0

    var tree_factor := clampf(
        tree * tree_zone * (1.0 - rock) * (1.0 - snow) * 1.45,
        0.0,
        1.0
    )
    var understory_factor := clampf(
        vegetation * (1.0 - 0.65 * rock) * (1.0 - 0.82 * snow) * 1.25,
        0.0,
        1.0
    )
    var rock_factor := clampf(rock * (0.65 + 0.55 * (1.0 - vegetation)), 0.0, 1.0)
    return Vector3(tree_factor, understory_factor, rock_factor)

func _set_environment_meshes(environment: Dictionary) -> void:
    if not _vendor_ready:
        return
    var tree_asset := _tree_asset(environment)
    if tree_asset != _current_tree_asset:
        var tree_mesh := _asset_mesh(tree_asset)
        if tree_mesh != null:
            _tree_batch.multimesh.mesh = tree_mesh
            _current_tree_asset = tree_asset
    var mid_tree_asset := _mid_tree_asset(environment)
    if mid_tree_asset != _current_mid_tree_asset:
        var mid_tree_mesh := _asset_mesh(mid_tree_asset)
        if mid_tree_mesh != null:
            _mid_tree_batch.multimesh.mesh = mid_tree_mesh
            _current_mid_tree_asset = mid_tree_asset
    var understory_asset := _understory_asset(environment)
    if understory_asset != _current_understory_asset:
        var understory_mesh := _asset_mesh(understory_asset)
        if understory_mesh != null:
            _understory_batch.multimesh.mesh = understory_mesh
            _current_understory_asset = understory_asset

func _rebuild_needed(position: Vector3, forward: Vector3) -> bool:
    if _last_forward.length_squared() < 0.001:
        return true
    var moved := Vector2(position.x - _last_origin.x, position.z - _last_origin.z).length()
    if moved >= REBUILD_DISTANCE_M:
        return true
    var normalized := forward.normalized()
    return normalized.dot(_last_forward.normalized()) < REBUILD_DOT

func _candidate_position(
    position: Vector3,
    heading: float,
    seed: float,
    index: int,
    salt: float,
    inner_m: float,
    outer_m: float,
) -> Vector2:
    var u := fposmod(float(index) * (0.61803398875 + salt * 0.01) + 0.19 + salt, 1.0)
    var angle_offset := lerpf(-HALF_ANGLE_RAD, HALF_ANGLE_RAD, u)
    var phase := heading + angle_offset
    var ratio := sqrt(fposmod(float(index) * (0.754877666 + salt * 0.013) + 0.27, 1.0))
    var radius := lerpf(inner_m, outer_m, ratio)
    radius += sin(seed * 0.00019 + float(index) * (1.71 + salt)) * 1.8
    return Vector2(
        clampf(position.x + sin(phase) * radius, -_half_m + 5.0, _half_m - 5.0),
        clampf(position.z + cos(phase) * radius, -_half_m + 5.0, _half_m - 5.0),
    )

func _inside_corridor(
    position: Vector3,
    forward: Vector3,
    point: Vector2,
    half_width_m: float,
) -> bool:
    var flat_forward := Vector2(forward.x, forward.z).normalized()
    if flat_forward.length_squared() < 0.001:
        flat_forward = Vector2(0.0, -1.0)
    var right := Vector2(-flat_forward.y, flat_forward.x)
    var delta := point - Vector2(position.x, position.z)
    var longitudinal := delta.dot(flat_forward)
    if longitudinal <= 0.0 or longitudinal > CORRIDOR_LENGTH_M:
        return false
    var lateral := absf(delta.dot(right))
    return lateral < half_width_m

func rebuild(
    position: Vector3,
    forward: Vector3,
    region_id: String,
    force: bool = false,
) -> void:
    if (
        _tree_batch == null
        or _mid_tree_batch == null
        or _understory_batch == null
        or _rock_batch == null
    ):
        return
    if not _vendor_ready:
        _tree_batch.multimesh.visible_instance_count = 0
        _mid_tree_batch.multimesh.visible_instance_count = 0
        _understory_batch.multimesh.visible_instance_count = 0
        _rock_batch.multimesh.visible_instance_count = 0
        return
    if not force and not _rebuild_needed(position, forward):
        return

    if not region_id.is_empty():
        _last_region_id = region_id
    var effective_region := region_id if not region_id.is_empty() else _last_region_id
    var environment := _environment(effective_region)
    _set_environment_meshes(environment)
    var factors := _environment_factors(environment)
    var tree_target := clampi(int(round(TREE_BUDGET * factors.x)), 0, TREE_BUDGET)
    var mid_tree_target := clampi(
        int(round(MID_TREE_BUDGET * factors.x * 0.92)), 0, MID_TREE_BUDGET
    )
    var understory_target := clampi(
        int(round(UNDERSTORY_BUDGET * factors.y)), 0, UNDERSTORY_BUDGET
    )
    var rock_target := clampi(int(round(ROCK_BUDGET * factors.z)), 0, ROCK_BUDGET)

    var normalized := forward.normalized()
    if normalized.length_squared() < 0.001:
        normalized = Vector3(0.0, 0.0, -1.0)
    var heading := atan2(normalized.x, normalized.z)
    var cx := int(_cell_sampler.call(position.x))
    var cz := int(_cell_sampler.call(position.z))
    var seed := float(cx * 161803 + cz * 104729)

    var tree_count := 0
    var attempts := 0
    while tree_count < tree_target and attempts < TREE_BUDGET * 5:
        var p := _candidate_position(position, heading, seed, attempts, 0.11, 8.5, OUTER_M)
        attempts += 1
        if not bool(_allowed_sampler.call(p.x, p.y)):
            continue
        if _inside_corridor(
            position, normalized, p, CORRIDOR_TREE_ROCK_HALF_WIDTH_M
        ):
            continue
        var y := float(_height_sampler.call(p.x, p.y))
        var noise := 0.5 + 0.5 * sin(seed * 0.00023 + attempts * 2.17)
        var scale := 0.82 + 0.34 * noise
        var yaw := heading + noise * 2.7
        var basis := Basis(Vector3.UP, yaw).scaled(Vector3(scale, scale, scale))
        _tree_batch.multimesh.set_instance_transform(
            tree_count, Transform3D(basis, Vector3(p.x, y, p.y))
        )
        tree_count += 1

    var mid_tree_count := 0
    attempts = 0
    while mid_tree_count < mid_tree_target and attempts < MID_TREE_BUDGET * 5:
        var p := _candidate_position(
            position,
            heading,
            seed,
            attempts,
            0.23,
            MID_TREE_INNER_M,
            MID_TREE_OUTER_M
        )
        attempts += 1
        if not bool(_allowed_sampler.call(p.x, p.y)):
            continue
        if _inside_corridor(
            position, normalized, p, CORRIDOR_TREE_ROCK_HALF_WIDTH_M
        ):
            continue
        var y := float(_height_sampler.call(p.x, p.y))
        var noise := 0.5 + 0.5 * sin(seed * 0.00029 + attempts * 1.97)
        var scale := 0.62 + 0.30 * noise
        var yaw := heading + noise * 3.3
        var basis := Basis(Vector3.UP, yaw).scaled(Vector3(scale, scale, scale))
        _mid_tree_batch.multimesh.set_instance_transform(
            mid_tree_count, Transform3D(basis, Vector3(p.x, y, p.y))
        )
        mid_tree_count += 1

    var understory_count := 0
    attempts = 0
    while understory_count < understory_target and attempts < UNDERSTORY_BUDGET * 4:
        var p := _candidate_position(position, heading, seed, attempts, 0.37, INNER_M, 24.0)
        attempts += 1
        if not bool(_allowed_sampler.call(p.x, p.y)):
            continue
        if _inside_corridor(
            position, normalized, p, CORRIDOR_UNDERSTORY_HALF_WIDTH_M
        ):
            continue
        var y := float(_height_sampler.call(p.x, p.y))
        var noise := 0.5 + 0.5 * sin(seed * 0.00031 + attempts * 1.73)
        var scale := 0.55 + 0.42 * noise
        var basis := Basis(Vector3.UP, noise * 4.1).scaled(Vector3(scale, scale, scale))
        _understory_batch.multimesh.set_instance_transform(
            understory_count, Transform3D(basis, Vector3(p.x, y, p.y))
        )
        understory_count += 1

    var rock_count := 0
    attempts = 0
    while rock_count < rock_target and attempts < ROCK_BUDGET * 4:
        var p := _candidate_position(position, heading, seed, attempts, 0.73, INNER_M, 27.0)
        attempts += 1
        if not bool(_allowed_sampler.call(p.x, p.y)):
            continue
        if _inside_corridor(
            position, normalized, p, CORRIDOR_TREE_ROCK_HALF_WIDTH_M
        ):
            continue
        var y := float(_height_sampler.call(p.x, p.y))
        var noise := 0.5 + 0.5 * sin(seed * 0.00041 + attempts * 2.43)
        var scale := 0.48 + 0.48 * noise
        var basis := Basis(Vector3.UP, noise * 5.3).scaled(
            Vector3(scale, 0.65 + 0.45 * scale, scale)
        )
        _rock_batch.multimesh.set_instance_transform(
            rock_count, Transform3D(basis, Vector3(p.x, y, p.y))
        )
        rock_count += 1

    _tree_batch.multimesh.visible_instance_count = tree_count
    _mid_tree_batch.multimesh.visible_instance_count = mid_tree_count
    _understory_batch.multimesh.visible_instance_count = understory_count
    _rock_batch.multimesh.visible_instance_count = rock_count
    _last_origin = position
    _last_forward = normalized
    var signature := "%s|%d|%d|%d|%d|%s|%s|%s" % [
        effective_region,
        tree_count,
        mid_tree_count,
        understory_count,
        rock_count,
        _current_tree_asset.get_file(),
        _current_mid_tree_asset.get_file(),
        _current_understory_asset.get_file(),
    ]
    if signature != _last_logged_signature:
        print(
            "WORLD_MAP_HERO_NATURE region=%s trees=%d mid_trees=%d understory=%d rocks=%d tree_asset=%s mid_asset=%s under_asset=%s" % [
                effective_region,
                tree_count,
                mid_tree_count,
                understory_count,
                rock_count,
                _current_tree_asset.get_file(),
                _current_mid_tree_asset.get_file(),
                _current_understory_asset.get_file(),
            ]
        )
        _last_logged_signature = signature

func visible_counts() -> Vector3i:
    return Vector3i(
        0 if _tree_batch == null else _tree_batch.multimesh.visible_instance_count,
        0 if _understory_batch == null else _understory_batch.multimesh.visible_instance_count,
        0 if _rock_batch == null else _rock_batch.multimesh.visible_instance_count,
    )

func mid_tree_visible_count() -> int:
    return 0 if _mid_tree_batch == null else _mid_tree_batch.multimesh.visible_instance_count
