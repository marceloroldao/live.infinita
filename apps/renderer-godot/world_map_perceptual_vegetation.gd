extends RefCounted
# 008BH: local environmental vegetation materialized only near NOV.
# The persistent world remains authoritative elsewhere; this module is visual-only.

const TREE_BUDGET := 44
const UNDERGROWTH_BUDGET := 220
const TREE_LOAD_M := 100.0
const TREE_RETAIN_M := 125.0
const UNDERGROWTH_LOAD_M := 75.0
const UNDERGROWTH_RETAIN_M := 100.0
const REBUILD_DISTANCE_M := 10.0

const Residency = preload("res://nature_local_residency.gd")
var _tree_residency = Residency.new()
var _undergrowth_residency = Residency.new()

var _batch_factory: Callable
var _height_sampler: Callable
var _allowed_sampler: Callable
var _cell_sampler: Callable
var _half_m: float

var _trunks: MultiMeshInstance3D
var _canopies: MultiMeshInstance3D
var _undergrowth: MultiMeshInstance3D
var _environment_by_region: Dictionary = {}
var _environment_state_id := ""
var _last_origin := Vector3(999999.0, 0.0, 999999.0)
var _last_forward := Vector3.ZERO
var _last_region_id := ""
var _last_logged_tree_count := -1
var _last_logged_undergrowth_count := -1
var _last_logged_region := ""

func _init(
    batch_factory: Callable,
    height_sampler: Callable,
    allowed_sampler: Callable,
    cell_sampler: Callable,
    half_m: float,
) -> void:
    _batch_factory = batch_factory
    _height_sampler = height_sampler
    _allowed_sampler = allowed_sampler
    _cell_sampler = cell_sampler
    _half_m = half_m

func build(position: Vector3, forward: Vector3) -> void:
    var trunk_mesh := CylinderMesh.new()
    trunk_mesh.top_radius = 0.24
    trunk_mesh.bottom_radius = 0.42
    trunk_mesh.height = 4.4
    trunk_mesh.radial_segments = 5
    trunk_mesh.rings = 1

    var canopy_mesh := CylinderMesh.new()
    canopy_mesh.top_radius = 0.28
    canopy_mesh.bottom_radius = 2.25
    canopy_mesh.height = 6.6
    canopy_mesh.radial_segments = 5
    canopy_mesh.rings = 1

    var undergrowth_mesh := CylinderMesh.new()
    undergrowth_mesh.top_radius = 0.10
    undergrowth_mesh.bottom_radius = 0.48
    undergrowth_mesh.height = 0.95
    undergrowth_mesh.radial_segments = 4
    undergrowth_mesh.rings = 1

    _trunks = _batch_factory.call(
        "PerceptualTreeTrunks", trunk_mesh, Color("#65492f"), TREE_BUDGET
    )
    _canopies = _batch_factory.call(
        "PerceptualTreeCanopies", canopy_mesh, Color("#456f38"), TREE_BUDGET
    )
    _undergrowth = _batch_factory.call(
        "PerceptualUndergrowth", undergrowth_mesh, Color("#5f8d43"), UNDERGROWTH_BUDGET
    )
    rebuild(position, forward, "", true)

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

func environment_state_id() -> String:
    return _environment_state_id

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

func vegetation_factors(region_id: String) -> Vector2:
    var environment := _environment(region_id)
    if environment.is_empty():
        return Vector2(0.22, 0.38)

    var vegetation := clampf(float(environment.get("vegetation_density", 0.35)), 0.0, 1.0)
    var tree_suitability := clampf(float(environment.get("tree_suitability", 0.25)), 0.0, 1.0)
    var rock := clampf(float(environment.get("rock_exposure", 0.0)), 0.0, 1.0)
    var snow := clampf(float(environment.get("snow_cover", 0.0)), 0.0, 1.0)
    var forest_affinity := _ecological_affinity(environment, "forest_affinity")
    var meadow_affinity := _ecological_affinity(environment, "meadow_affinity")
    var shrub_affinity := _ecological_affinity(environment, "shrub_affinity")
    var wetland_affinity := _ecological_affinity(environment, "wetland_affinity")
    var alpine_affinity := _ecological_affinity(environment, "alpine_affinity")

    var tree_membership := clampf(
        0.08
        + 0.92 * forest_affinity
        + 0.32 * wetland_affinity
        + 0.22 * meadow_affinity
        + 0.10 * shrub_affinity
        - 0.82 * alpine_affinity,
        0.0,
        1.0
    )
    var tree_factor := clampf(
        tree_suitability
        * (0.60 + 0.80 * vegetation)
        * (1.0 - rock)
        * (1.0 - snow)
        * 1.55
        * tree_membership,
        0.0,
        1.0
    )
    var undergrowth_membership := clampf(
        0.25
        + 0.55 * meadow_affinity
        + 0.48 * shrub_affinity
        + 0.75 * forest_affinity
        + 0.40 * wetland_affinity
        - 0.65 * alpine_affinity,
        0.04,
        1.0
    )
    var undergrowth_factor := clampf(
        vegetation
        * (1.0 - 0.72 * rock)
        * (1.0 - 0.82 * snow)
        * 1.45
        * undergrowth_membership,
        0.04,
        1.0
    )
    return Vector2(tree_factor, undergrowth_factor)

func _rebuild_needed(position: Vector3, forward: Vector3) -> bool:
    if _last_forward.length_squared() < 0.001:
        return true
    var moved := Vector2(
        position.x - _last_origin.x,
        position.z - _last_origin.z
    ).length()
    if moved >= REBUILD_DISTANCE_M:
        return true
    return false

func rebuild(
    position: Vector3,
    forward: Vector3,
    region_id: String,
    force: bool = false,
) -> void:
    if _trunks == null or _canopies == null or _undergrowth == null:
        return
    if not force and not _rebuild_needed(position, forward):
        return

    if not region_id.is_empty():
        _last_region_id = region_id
    var effective_region_id := region_id if not region_id.is_empty() else _last_region_id

    var normalized := forward.normalized()
    if normalized.length_squared() < 0.001:
        normalized = Vector3(0.0, 0.0, -1.0)
    var factors := vegetation_factors(effective_region_id)
    var trees: Array = _tree_residency.update(position, TREE_BUDGET, factors.x, 12.0,
        TREE_LOAD_M, TREE_RETAIN_M, 11, _half_m, _allowed_sampler)
    var plants: Array = _undergrowth_residency.update(position, UNDERGROWTH_BUDGET, factors.y, 5.0,
        UNDERGROWTH_LOAD_M, UNDERGROWTH_RETAIN_M, 37, _half_m, _allowed_sampler)
    var tree_placed := 0
    for record in trees:
        if not record.has("trunk"):
            var p: Vector2 = record["point"]
            var noise: float = record["noise"]
            var y := float(_height_sampler.call(p.x, p.y))
            var height_scale := 0.86 + 0.58 * noise
            var trunk_width := 0.72 + 0.30 * noise
            var canopy_width := 0.72 + 0.48 * noise
            var trunk_basis := Basis(Vector3.UP, noise * TAU).scaled(Vector3(trunk_width, height_scale, trunk_width))
            var canopy_basis := Basis(Vector3.UP, noise * TAU + 0.15).scaled(Vector3(canopy_width, height_scale, canopy_width))
            record["trunk"] = Transform3D(trunk_basis, Vector3(p.x, y + 2.2 * height_scale, p.y))
            record["canopy"] = Transform3D(canopy_basis, Vector3(p.x, y + 5.5 * height_scale, p.y))
        _trunks.multimesh.set_instance_transform(tree_placed, record["trunk"])
        _canopies.multimesh.set_instance_transform(tree_placed, record["canopy"])
        tree_placed += 1
    var undergrowth_placed := 0
    for record in plants:
        if not record.has("transform"):
            var p: Vector2 = record["point"]
            var noise: float = record["noise"]
            var scale := 0.45 + 0.80 * noise
            var basis := Basis(Vector3.UP, noise * TAU).scaled(Vector3(scale, scale * (0.72 + 0.38 * noise), scale))
            record["transform"] = Transform3D(basis, Vector3(p.x, float(_height_sampler.call(p.x, p.y)) + 0.48 * scale, p.y))
        _undergrowth.multimesh.set_instance_transform(undergrowth_placed, record["transform"])
        undergrowth_placed += 1

    _trunks.multimesh.visible_instance_count = tree_placed
    _canopies.multimesh.visible_instance_count = tree_placed
    _undergrowth.multimesh.visible_instance_count = undergrowth_placed
    preload("res://nature_batch_collision.gd").sync(_trunks, trees.map(func(row): return row["trunk"]), true)
    preload("res://nature_batch_collision.gd").sync(_undergrowth, plants.map(func(row): return row["transform"]))
    _last_origin = position
    _last_forward = normalized
    if (
        tree_placed != _last_logged_tree_count
        or undergrowth_placed != _last_logged_undergrowth_count
        or effective_region_id != _last_logged_region
    ):
        print(
            "WORLD_MAP_PERCEPTUAL_VEGETATION region=%s trees=%d undergrowth=%d env=%s" % [
                effective_region_id, tree_placed, undergrowth_placed, _environment_state_id
            ]
        )
        _last_logged_tree_count = tree_placed
        _last_logged_undergrowth_count = undergrowth_placed
        _last_logged_region = effective_region_id

func tree_visible_count() -> int:
    return 0 if _trunks == null else _trunks.multimesh.visible_instance_count

func undergrowth_visible_count() -> int:
    return 0 if _undergrowth == null else _undergrowth.multimesh.visible_instance_count
