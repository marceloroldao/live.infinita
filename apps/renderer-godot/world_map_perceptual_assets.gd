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
const TREE_LOAD_M := 60.0
const TREE_RETAIN_M := 85.0
const MID_TREE_LOAD_M := 85.0
const MID_TREE_RETAIN_M := 110.0
const UNDERSTORY_LOAD_M := 50.0
const UNDERSTORY_RETAIN_M := 75.0
const REBUILD_DISTANCE_M := 9.0

const Residency = preload("res://nature_local_residency.gd")
var _residencies: Dictionary = {}
var _asset_batches: Dictionary = {}
var _counts := Vector3i.ZERO
var _mid_count := 0

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

func _ecological_affinity(environment: Dictionary, key: String) -> float:
    if environment.has(key):
        return clampf(float(environment.get(key, 0.0)), 0.0, 1.0)
    var zone := str(environment.get("ecological_zone", "sparse"))
    match key:
        "forest_affinity":
            if zone == "forest":
                return 1.0
            if zone == "wetland":
                return 0.35
            if zone == "meadow":
                return 0.18
        "meadow_affinity":
            if zone in ["meadow", "alpine_meadow"]:
                return 0.85
            if zone == "shrubland":
                return 0.35
        "shrub_affinity":
            if zone == "shrubland":
                return 0.85
            if zone == "meadow":
                return 0.30
        "wetland_affinity":
            if zone == "wetland":
                return 1.0
        "alpine_affinity":
            if zone == "snowfield":
                return 1.0
            if zone == "alpine_rock":
                return 0.92
            if zone == "alpine_meadow":
                return 0.65
    return 0.0

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
    var forest_affinity := _ecological_affinity(environment, "forest_affinity")
    var meadow_affinity := _ecological_affinity(environment, "meadow_affinity")
    var shrub_affinity := _ecological_affinity(environment, "shrub_affinity")
    var wetland_affinity := _ecological_affinity(environment, "wetland_affinity")
    var alpine_affinity := _ecological_affinity(environment, "alpine_affinity")

    var tree_membership := clampf(
        0.06
        + 0.94 * forest_affinity
        + 0.26 * wetland_affinity
        + 0.16 * meadow_affinity
        + 0.08 * shrub_affinity
        - 0.84 * alpine_affinity,
        0.0,
        1.0
    )
    var tree_factor := clampf(
        tree * tree_membership * (1.0 - rock) * (1.0 - snow) * 1.45,
        0.0,
        1.0
    )
    var understory_membership := clampf(
        0.22
        + 0.52 * meadow_affinity
        + 0.45 * shrub_affinity
        + 0.68 * forest_affinity
        + 0.36 * wetland_affinity
        - 0.62 * alpine_affinity,
        0.0,
        1.0
    )
    var understory_factor := clampf(
        vegetation
        * (1.0 - 0.65 * rock)
        * (1.0 - 0.82 * snow)
        * 1.25
        * understory_membership,
        0.0,
        1.0
    )
    var rock_factor := clampf(
        rock
        * (0.65 + 0.55 * (1.0 - vegetation))
        * (0.72 + 0.45 * alpine_affinity),
        0.0,
        1.0
    )
    return Vector3(tree_factor, understory_factor, rock_factor)

func _rebuild_needed(position: Vector3, forward: Vector3) -> bool:
    if _last_forward.length_squared() < 0.001:
        return true
    var moved := Vector2(position.x - _last_origin.x, position.z - _last_origin.z).length()
    if moved >= REBUILD_DISTANCE_M:
        return true
    return false

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
    var factors := _environment_factors(environment)
    var tree_count := _stable_layer("tree", _tree_batch, position, TREE_BUDGET, factors.x, 12.0, TREE_LOAD_M, TREE_RETAIN_M, 101, _tree_asset(environment), true)
    var mid_tree_count := _stable_layer("mid_tree", _mid_tree_batch, position, MID_TREE_BUDGET, factors.x * 0.92, 17.0, MID_TREE_LOAD_M, MID_TREE_RETAIN_M, 123, _mid_tree_asset(environment), true)
    var understory_count := _stable_layer("plant", _understory_batch, position, UNDERSTORY_BUDGET, factors.y, 7.0, UNDERSTORY_LOAD_M, UNDERSTORY_RETAIN_M, 137, _understory_asset(environment), false)
    var rock_count := _stable_layer("rock", _rock_batch, position, ROCK_BUDGET, factors.z, 13.0, TREE_LOAD_M, TREE_RETAIN_M, 173, ROCK, false)
    _counts = Vector3i(tree_count, understory_count, rock_count)
    _mid_count = mid_tree_count
    _current_tree_asset = _tree_asset(environment)
    _current_mid_tree_asset = _mid_tree_asset(environment)
    _current_understory_asset = _understory_asset(environment)
    var normalized := forward.normalized()
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

func _stable_layer(
    layer: String, primary: MultiMeshInstance3D, position: Vector3, budget: int,
    density: float, spacing: float, load_radius: float, retain_radius: float,
    salt: int, asset: String, tree: bool,
) -> int:
    if not _residencies.has(layer):
        _residencies[layer] = Residency.new()
        _asset_batches[layer] = {}
    var residency = _residencies[layer]
    var rows: Array = residency.update(position, budget, density, spacing,
        load_radius, retain_radius, salt, _half_m, _allowed_sampler)
    var groups: Dictionary = {}
    for row in rows:
        if not row.has("asset"):
            row["asset"] = asset
            var p: Vector2 = row["point"]
            var noise: float = row["noise"]
            var scale := 0.82 + 0.34 * noise if tree else 0.55 + 0.42 * noise
            if layer == "mid_tree":
                scale = 0.62 + 0.30 * noise
            if layer == "rock":
                scale = 0.48 + 0.48 * noise
            var basis := Basis(Vector3.UP, noise * TAU).scaled(Vector3.ONE * scale)
            row["transform"] = Transform3D(basis, Vector3(p.x, float(_height_sampler.call(p.x, p.y)), p.y))
        var identity: String = row["asset"]
        if not groups.has(identity):
            groups[identity] = []
        groups[identity].append(row)
    var batches: Dictionary = _asset_batches[layer]
    for identity in groups:
        if not batches.has(identity):
            var mesh := _asset_mesh(identity)
            if mesh == null:
                continue
            var batch: MultiMeshInstance3D = primary if batches.is_empty() else _batch(layer + "Variant", mesh, budget)
            batch.multimesh.mesh = mesh
            batches[identity] = batch
    for identity in batches:
        var batch: MultiMeshInstance3D = batches[identity]
        var items: Array = groups.get(identity, [])
        for i in range(items.size()):
            batch.multimesh.set_instance_transform(i, items[i]["transform"])
        batch.multimesh.visible_instance_count = items.size()
        if tree or layer == "rock":
            preload("res://nature_batch_collision.gd").sync(batch, tree)
    return rows.size()

func visible_counts() -> Vector3i:
    return _counts

func mid_tree_visible_count() -> int:
    return _mid_count
