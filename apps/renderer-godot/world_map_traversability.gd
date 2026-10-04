extends RefCounted

const MAP_MARGIN := 1.0
const RIVER_X := 32.0
const RIVER_HALF_WIDTH := 10.0
const BRIDGE_Z := -32.0
const BRIDGE_HALF_WIDTH := 3.1
const BRIDGE_MIN_X := 7.0
const BRIDGE_MAX_X := 57.0
const MAX_STEP_M := 1.25
const CAPSULE_RADIUS := 0.44
const CAPSULE_HEIGHT := 1.8
const MAX_COLLISION_HITS := 8

var _walk_height: Callable
var _half_m := 512.0
var _dynamic_surface: Callable

func _init(walk_height: Callable, half_m: float = 512.0, dynamic_surface: Callable = Callable()) -> void:
    _walk_height = walk_height
    _half_m = half_m
    _dynamic_surface = dynamic_surface

func surface(position: Vector3) -> Dictionary:
    if absf(position.x) > _half_m - MAP_MARGIN or absf(position.z) > _half_m - MAP_MARGIN:
        return {"walkable": false, "surface": "boundary", "reason": "map_boundary"}
    var on_bridge := (
        position.x >= BRIDGE_MIN_X and position.x <= BRIDGE_MAX_X
        and absf(position.z - BRIDGE_Z) <= BRIDGE_HALF_WIDTH
    )
    if on_bridge:
        return {"walkable": true, "surface": "bridge", "reason": ""}
    if absf(position.x - RIVER_X) <= RIVER_HALF_WIDTH:
        return {"walkable": false, "surface": "water", "reason": "river_without_bridge"}
    if _dynamic_surface.is_valid():
        var dynamic = _dynamic_surface.call(position.x, position.z)
        if typeof(dynamic) == TYPE_DICTIONARY and not bool(dynamic.get("walkable", true)):
            return dynamic
    return {"walkable": true, "surface": "terrain", "reason": ""}

func ground_position(x: float, z: float) -> Vector3:
    return Vector3(x, float(_walk_height.call(x, z)), z)

func find_detour(
    current: Vector3,
    route_target: Vector3,
    step_distance: float,
    space_state: PhysicsDirectSpaceState3D = null
) -> Dictionary:
    var origin := Vector2(current.x, current.z)
    var goal := Vector2(route_target.x, route_target.z)
    var desired := goal - origin
    if desired.length_squared() < 0.0001:
        return {"allowed": false, "position": current, "reason": "no_detour_target"}
    desired = desired.normalized()

    # Ordered symmetric probes make the local choice deterministic while still
    # allowing the explorer to bend around water, steep terrain, or obstacles.
    var probe_angles := [35.0, -35.0, 70.0, -70.0, 105.0, -105.0, 140.0, -140.0]
    var best: Dictionary = {}
    var best_score := INF
    for angle in probe_angles:
        var direction := desired.rotated(deg_to_rad(float(angle)))
        var flat := origin + direction * step_distance
        var candidate := Vector3(flat.x, current.y, flat.y)
        var policy := validate_step(current, candidate, space_state)
        if not bool(policy.get("allowed", false)):
            continue
        var resolved: Vector3 = policy.get("position", current)
        var remaining := Vector2(resolved.x, resolved.z).distance_to(goal)
        var score := remaining + absf(float(angle)) * 0.002
        if score < best_score:
            best_score = score
            best = policy.duplicate(true)
            best["detour"] = true
            best["detour_angle_deg"] = float(angle)
    if best.is_empty():
        return {"allowed": false, "position": current, "reason": "detour_unavailable"}
    return best

func validate_step(current: Vector3, candidate: Vector3, space_state: PhysicsDirectSpaceState3D = null) -> Dictionary:
    var length_m := Vector2(candidate.x - current.x, candidate.z - current.z).length()
    var count := maxi(1, ceili(length_m / 0.2))
    for i in range(1, count):
        var intermediate := current.lerp(candidate, float(i) / count)
        var probe := ground_position(intermediate.x, intermediate.z)
        var classification := surface(probe)
        if not bool(classification.get("walkable", false)) or absf(probe.y - current.y) > MAX_STEP_M:
            return {"allowed": false, "position": current, "reason": classification.get("reason", "step_too_high"), "surface": classification.get("surface", "terrain")}
    if space_state != null and length_m > 0.001:
        var sweep_shape := CapsuleShape3D.new()
        sweep_shape.radius = CAPSULE_RADIUS
        sweep_shape.height = CAPSULE_HEIGHT
        var sweep := PhysicsShapeQueryParameters3D.new()
        sweep.shape = sweep_shape
        sweep.transform = Transform3D(Basis.IDENTITY, current + Vector3(0, CAPSULE_HEIGHT * 0.5, 0))
        sweep.motion = Vector3(candidate.x - current.x, 0, candidate.z - current.z)
        sweep.collision_mask = 1
        var fractions := space_state.cast_motion(sweep)
        if fractions[0] < 1.0:
            return {"allowed": false, "position": current, "reason": "static_obstacle", "surface": "terrain", "collisions": 1}
    var target := ground_position(candidate.x, candidate.z)
    var classification := surface(target)
    if not bool(classification.get("walkable", false)):
        return {
            "allowed": false,
            "position": current,
            "surface": classification.get("surface", "unknown"),
            "reason": classification.get("reason", "blocked"),
            "collisions": 0,
        }

    var step_height := absf(target.y - current.y)
    if step_height > MAX_STEP_M:
        return {
            "allowed": false,
            "position": current,
            "surface": classification.get("surface", "terrain"),
            "reason": "step_too_high",
            "collisions": 0,
            "step_height": step_height,
        }

    if space_state != null:
        var capsule := CapsuleShape3D.new()
        capsule.radius = CAPSULE_RADIUS
        capsule.height = CAPSULE_HEIGHT
        var query := PhysicsShapeQueryParameters3D.new()
        query.shape = capsule
        query.transform = Transform3D(Basis.IDENTITY, target + Vector3(0, CAPSULE_HEIGHT * 0.5, 0))
        query.collision_mask = 1
        query.collide_with_areas = false
        query.collide_with_bodies = true
        var hits := space_state.intersect_shape(query, MAX_COLLISION_HITS)
        if not hits.is_empty():
            return {
                "allowed": false,
                "position": current,
                "surface": classification.get("surface", "terrain"),
                "reason": "static_obstacle",
                "collisions": hits.size(),
            }

    return {
        "allowed": true,
        "position": target,
        "surface": classification.get("surface", "terrain"),
        "reason": "",
        "collisions": 0,
        "step_height": step_height,
    }
