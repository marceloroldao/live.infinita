extends RefCounted

const Traversability = preload("res://world_map_traversability.gd")
const NovCharacterVisual = preload("res://nov_character_visual.gd")
const SPEED_MPS := 13.0
const BODY_CENTER_Y := 0.9

var _experience = preload("res://nov_navigation_experience.gd").new()
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
    auto_route: bool = true,
    speed_mps: float = SPEED_MPS
) -> Dictionary:
    var candidate := current
    var manual := input_axis.length_squared() > 0.01
    if manual:
        candidate.x += input_axis.x * speed_mps * delta
        candidate.z += input_axis.y * speed_mps * delta
    elif auto_route:
        var flat_goal: Vector2 = _experience.target(Vector2(current.x, current.z), Vector2(route_target.x, route_target.z))
        var flat := Vector2(current.x, current.z).move_toward(flat_goal, speed_mps * delta)
        candidate.x = flat.x
        candidate.z = flat.y

    var policy: Dictionary = _traversability.validate_step(current, candidate, space_state)
    policy["manual"] = manual
    if not bool(policy.get("allowed", false)):
        if auto_route and not manual:
            _experience.blocked()
        policy["reached"] = false
        body.velocity = Vector3.ZERO
        return policy

    var target: Vector3 = policy.get("position", current)
    snap_body(body, current)
    var displacement := Vector3(target.x - current.x, 0, target.z - current.z)
    # Swept motion uses the requested dt even in presentation smoke calls.
    body.move_and_collide(displacement)

    var resolved: Vector3 = _traversability.ground_position(body.position.x, body.position.z)
    body.position.y = resolved.y + BODY_CENTER_Y
    var collisions := 1 if Vector2(resolved.x - target.x, resolved.z - target.z).length() > 0.02 else 0
    policy["position"] = resolved
    policy["collisions"] = collisions
    if collisions > 0:
        policy["reason"] = "static_obstacle"
    if auto_route and not manual:
        if collisions > 0 or (displacement.length() > 0.001 and resolved.distance_to(current) < 0.0001):
            _experience.blocked()
        elif Vector2(resolved.x, resolved.z).distance_to(_experience.pending) < 0.03:
            _experience.arrived(Vector2(route_target.x, route_target.z))
    policy["reached"] = (
        auto_route
        and not manual
        and Vector2(resolved.x, resolved.z).distance_to(Vector2(route_target.x, route_target.z)) < 0.1
    )
    return policy
