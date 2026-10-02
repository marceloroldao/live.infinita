extends RefCounted

const Traversability = preload("res://world_map_traversability.gd")
const NovCharacterVisual = preload("res://nov_character_visual.gd")
const SPEED_MPS := 13.0
const BODY_CENTER_Y := 0.9

var _traversability: RefCounted

func _init(walk_height: Callable, half_m: float = 512.0, dynamic_surface: Callable = Callable()) -> void:
    _traversability = Traversability.new(walk_height, half_m, dynamic_surface)

func create_body(parent: Node3D, _material: Material) -> CharacterBody3D:
    var body := CharacterBody3D.new()
    body.name = "LocalExplorerBody"
    body.collision_layer = 0
    body.collision_mask = 1
    body.safe_margin = 0.04
    parent.add_child(body)

    var visual := NovCharacterVisual.new()
    visual.name = "NovVisual"
    body.add_child(visual)

    var shape := CapsuleShape3D.new()
    shape.radius = 0.44
    shape.height = 1.8
    var collision := CollisionShape3D.new()
    collision.shape = shape
    body.add_child(collision)
    return body

func snap_body(body: CharacterBody3D, ground_position: Vector3) -> void:
    body.position = ground_position + Vector3(0, BODY_CENTER_Y, 0)
    body.velocity = Vector3.ZERO

func advance(
    current: Vector3,
    input_axis: Vector2,
    route_target: Vector3,
    delta: float,
    body: CharacterBody3D,
    space_state: PhysicsDirectSpaceState3D,
    auto_route: bool = true
) -> Dictionary:
    var candidate := current
    var manual := input_axis.length_squared() > 0.01
    if manual:
        candidate.x += input_axis.x * SPEED_MPS * delta
        candidate.z += input_axis.y * SPEED_MPS * delta
    elif auto_route:
        var flat := Vector2(current.x, current.z).move_toward(
            Vector2(route_target.x, route_target.z), SPEED_MPS * delta
        )
        candidate.x = flat.x
        candidate.z = flat.y

    var policy: Dictionary = _traversability.validate_step(current, candidate, space_state)
    policy["manual"] = manual
    if not bool(policy.get("allowed", false)) and auto_route and not manual:
        var direct_reason := str(policy.get("reason", "blocked"))
        var step_distance := SPEED_MPS * delta
        var detour: Dictionary = _traversability.find_detour(
            current, route_target, step_distance, space_state
        )
        if bool(detour.get("allowed", false)):
            policy = detour
            policy["manual"] = false
            policy["direct_block_reason"] = direct_reason
    if not bool(policy.get("allowed", false)):
        policy["reached"] = false
        body.velocity = Vector3.ZERO
        return policy

    var target: Vector3 = policy.get("position", current)
    snap_body(body, current)
    var displacement := Vector3(target.x - current.x, 0, target.z - current.z)
    body.velocity = displacement / maxf(delta, 0.001)
    body.move_and_slide()

    var resolved: Vector3 = _traversability.ground_position(body.position.x, body.position.z)
    body.position.y = resolved.y + BODY_CENTER_Y
    var collisions := body.get_slide_collision_count()
    policy["position"] = resolved
    policy["collisions"] = collisions
    if collisions > 0:
        policy["reason"] = "static_obstacle"
    policy["reached"] = (
        auto_route
        and not manual
        and Vector2(resolved.x, resolved.z).distance_to(Vector2(route_target.x, route_target.z)) < 0.1
    )
    return policy
