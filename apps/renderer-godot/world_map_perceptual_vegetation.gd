extends RefCounted
# 008BH: local environmental vegetation materialized only near NOV.
# The persistent world remains authoritative elsewhere; this module is visual-only.

const TREE_BUDGET := 44
const UNDERGROWTH_BUDGET := 220
const TREE_INNER_M := 50.0
const TREE_OUTER_M := 90.0
const UNDERGROWTH_INNER_M := 28.0
const UNDERGROWTH_OUTER_M := 64.0
const HALF_ANGLE_RAD := 1.30
const REBUILD_DISTANCE_M := 10.0
const REBUILD_DOT := 0.94

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

func vegetation_factors(region_id: String) -> Vector2:
    var environment := _environment(region_id)
    if environment.is_empty():
        return Vector2(0.22, 0.38)

    var vegetation := clampf(float(environment.get("vegetation_density", 0.35)), 0.0, 1.0)
    var tree_suitability := clampf(float(environment.get("tree_suitability", 0.25)), 0.0, 1.0)
    var rock := clampf(float(environment.get("rock_exposure", 0.0)), 0.0, 1.0)
    var snow := clampf(float(environment.get("snow_cover", 0.0)), 0.0, 1.0)
    var zone := str(environment.get("ecological_zone", "sparse"))

    var zone_tree_multiplier := 0.20
    match zone:
        "forest":
            zone_tree_multiplier = 1.0
        "wetland":
            zone_tree_multiplier = 0.55
        "meadow":
            zone_tree_multiplier = 0.42
        "shrubland":
            zone_tree_multiplier = 0.22
        "alpine_meadow":
            zone_tree_multiplier = 0.08
        "alpine_rock", "snowfield":
            zone_tree_multiplier = 0.0

    var tree_factor := clampf(
        tree_suitability
        * (0.60 + 0.80 * vegetation)
        * (1.0 - rock)
        * (1.0 - snow)
        * 1.55
        * zone_tree_multiplier,
        0.0,
        1.0
    )
    var undergrowth_factor := clampf(
        vegetation * (1.0 - 0.72 * rock) * (1.0 - 0.82 * snow) * 1.45,
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
    var normalized := forward.normalized()
    return normalized.dot(_last_forward.normalized()) < REBUILD_DOT

func _tree_radius(seed: float, index: int) -> float:
    var radial_ratio := sqrt(fposmod(float(index) * 0.754877666 + 0.31, 1.0))
    return (
        lerpf(TREE_INNER_M, TREE_OUTER_M, radial_ratio)
        + sin(seed * 0.00017 + float(index) * 1.93) * 3.2
    )

func _undergrowth_radius(seed: float, index: int) -> float:
    var radial_ratio := sqrt(fposmod(float(index) * 0.438579021 + 0.11, 1.0))
    return (
        lerpf(UNDERGROWTH_INNER_M, UNDERGROWTH_OUTER_M, radial_ratio)
        + sin(seed * 0.00031 + float(index) * 1.71) * 2.0
    )

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
    var heading := atan2(normalized.x, normalized.z)
    var factors := vegetation_factors(effective_region_id)
    var tree_target := clampi(
        int(round(float(TREE_BUDGET) * factors.x)),
        0,
        TREE_BUDGET
    )
    var undergrowth_target := clampi(
        int(round(float(UNDERGROWTH_BUDGET) * factors.y)),
        0,
        UNDERGROWTH_BUDGET
    )
    var cx := int(_cell_sampler.call(position.x))
    var cz := int(_cell_sampler.call(position.z))
    var seed := float(cx * 104729 + cz * 130363)

    var tree_placed := 0
    var tree_attempt := 0
    while tree_placed < tree_target and tree_attempt < TREE_BUDGET * 5:
        var i := tree_attempt
        tree_attempt += 1
        var u := fposmod(float(i) * 0.61803398875 + 0.17, 1.0)
        var angle_offset := lerpf(-HALF_ANGLE_RAD, HALF_ANGLE_RAD, u)
        var phase := heading + angle_offset
        var radius := _tree_radius(seed, i)
        var x := clampf(position.x + sin(phase) * radius, -_half_m + 8.0, _half_m - 8.0)
        var z := clampf(position.z + cos(phase) * radius, -_half_m + 8.0, _half_m - 8.0)
        if not bool(_allowed_sampler.call(x, z)):
            continue
        var y := float(_height_sampler.call(x, z))
        var scale_noise := 0.5 + 0.5 * sin(seed * 0.00023 + float(i) * 2.47)
        var width_noise := 0.5 + 0.5 * sin(seed * 0.00037 + float(i) * 1.37)
        var height_scale := 0.86 + 0.58 * scale_noise
        var trunk_width := 0.72 + 0.30 * width_noise
        var canopy_width := 0.72 + 0.48 * width_noise
        var yaw := phase * 0.41 + width_noise * 0.7
        var trunk_basis := Basis(Vector3.UP, yaw).scaled(
            Vector3(trunk_width, height_scale, trunk_width)
        )
        var canopy_basis := Basis(Vector3.UP, yaw + 0.15).scaled(
            Vector3(canopy_width, height_scale, canopy_width)
        )
        _trunks.multimesh.set_instance_transform(
            tree_placed,
            Transform3D(trunk_basis, Vector3(x, y + 2.2 * height_scale, z))
        )
        _canopies.multimesh.set_instance_transform(
            tree_placed,
            Transform3D(canopy_basis, Vector3(x, y + 5.5 * height_scale, z))
        )
        tree_placed += 1

    var undergrowth_placed := 0
    var undergrowth_attempt := 0
    while undergrowth_placed < undergrowth_target and undergrowth_attempt < UNDERGROWTH_BUDGET * 4:
        var i := undergrowth_attempt
        undergrowth_attempt += 1
        var u := fposmod(float(i) * 0.569840291 + 0.43, 1.0)
        var angle_offset := lerpf(-HALF_ANGLE_RAD, HALF_ANGLE_RAD, u)
        var phase := heading + angle_offset
        var radius := _undergrowth_radius(seed, i)
        var x := clampf(position.x + sin(phase) * radius, -_half_m + 5.0, _half_m - 5.0)
        var z := clampf(position.z + cos(phase) * radius, -_half_m + 5.0, _half_m - 5.0)
        if not bool(_allowed_sampler.call(x, z)):
            continue
        var y := float(_height_sampler.call(x, z))
        var scale_noise := 0.5 + 0.5 * sin(seed * 0.00041 + float(i) * 2.21)
        var scale := 0.45 + 0.80 * scale_noise
        var basis := Basis(Vector3.UP, phase * 0.73).scaled(
            Vector3(scale, scale * (0.72 + 0.38 * scale_noise), scale)
        )
        _undergrowth.multimesh.set_instance_transform(
            undergrowth_placed,
            Transform3D(basis, Vector3(x, y + 0.48 * scale, z))
        )
        undergrowth_placed += 1

    _trunks.multimesh.visible_instance_count = tree_placed
    _canopies.multimesh.visible_instance_count = tree_placed
    _undergrowth.multimesh.visible_instance_count = undergrowth_placed
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
