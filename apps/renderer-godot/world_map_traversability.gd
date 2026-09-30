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

func _init(walk_height: Callable, half_m: float = 512.0) -> void:
    _walk_height = walk_height
    _half_m = half_m

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
    return {"walkable": true, "surface": "terrain", "reason": ""}

func ground_position(x: float, z: float) -> Vector3:
    return Vector3(x, float(_walk_height.call(x, z)), z)

func validate_step(current: Vector3, candidate: Vector3, space_state: PhysicsDirectSpaceState3D = null) -> Dictionary:
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
