extends RefCounted

const Traversability = preload("res://world_map_traversability.gd")
const NovCharacterVisual = preload("res://nov_character_visual.gd")
const SPEED_MPS := 13.0
const BODY_CENTER_Y := 0.9

var _experience = preload("res://nov_navigation_experience.gd").new()
var _traversability: RefCounted
var route_goal_id := ""
var _inference_log_at := 0
var _working_memory_log_at := 0
var _episodes = preload("res://nov_navigation_episodes.gd").new()

func _init(walk_height: Callable, half_m: float = 512.0, dynamic_surface: Callable = Callable()) -> void:
    _traversability = Traversability.new(walk_height, half_m, dynamic_surface)
    _episodes.action_completed.connect(Callable(_experience.working_memory, "observe_completed"))
    _experience.working_memory.promotion_ready.connect(Callable(_episodes, "flush"))

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
    if _experience.working_memory.enabled and Time.get_ticks_msec() >= _working_memory_log_at:
        _working_memory_log_at = Time.get_ticks_msec() + 30000
        print("NOV_WORKING_MEMORY_STATUS entries=%d causal_reuses=%d promoted=%d" % [_experience.working_memory.entries.size(), _experience.working_memory.causal_reuses, _experience.working_memory.promoted.size()])
    var candidate := current
    var manual := input_axis.length_squared() > 0.01
    if manual:
        candidate.x += input_axis.x * speed_mps * delta
        candidate.z += input_axis.y * speed_mps * delta
    elif auto_route:
        var flat_goal: Vector2 = _experience.target(Vector2(current.x, current.z), Vector2(route_target.x, route_target.z),
            func(point: Vector2) -> Dictionary: return _sense_ahead(current, point, space_state, Vector2(route_target.x, route_target.z)),
            func(start: Vector2, end: Vector2) -> bool:
                var grounded: Vector3 = _traversability.ground_position(start.x,start.y)
                var sensed: Dictionary = _sense_ahead(grounded,end,space_state,end)
                return bool(sensed.get("allowed",false)) and bool(sensed.get("clear_ahead",false)))
        if Time.get_ticks_msec() >= _inference_log_at and _experience.last_decision_source == "memoria.ia":
            _inference_log_at = Time.get_ticks_msec() + 10000
            print("NOV_NAVIGATION_INFERENCE source=memoria.ia observation=%s decisions=%d anticipations=%d" % [
                _experience.last_observation_id, _experience.memory_decisions, _experience.anticipated_avoidances])
        var flat := Vector2(current.x, current.z).move_toward(flat_goal, speed_mps * delta)
        candidate.x = flat.x
        candidate.z = flat.y

    var policy: Dictionary = _traversability.validate_step(current, candidate, space_state)
    policy["route_goal_id"] = route_goal_id
    if _experience._route_search.running and not manual:
        policy["reason"] = "route_search_in_progress"
    policy["manual"] = manual
    policy["decision_source"] = _experience.last_decision_source
    policy["memory_observation_id"] = _experience.last_observation_id
    policy["working_memory_session"] = _experience.working_memory.session
    policy["working_memory_key"] = _experience.working_memory_key
    policy["working_memory_changed_choice"] = _experience.working_memory_changed_choice
    if not bool(policy.get("allowed", false)):
        if auto_route and not manual:
            _experience.blocked()
        policy["reached"] = false
        body.velocity = Vector3.ZERO
        if auto_route and not manual:
            _episodes.observe(_experience.decision_serial, current, route_target, _experience.pending, _experience.decision_evidence, policy)
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
        elif _experience.active and Vector2(resolved.x, resolved.z).distance_to(_experience.pending) < 0.03:
            _experience.arrived(Vector2(route_target.x, route_target.z))
    policy["reached"] = (
        auto_route
        and not manual
        and Vector2(resolved.x, resolved.z).distance_to(Vector2(route_target.x, route_target.z)) < 0.1
    )
    if auto_route and not manual:
        _episodes.observe(_experience.decision_serial, current, route_target, _experience.pending, _experience.decision_evidence, policy)
    return policy

func _sense_ahead(current: Vector3, point: Vector2, space_state: PhysicsDirectSpaceState3D, goal: Vector2) -> Dictionary:
    var flat := Vector2(current.x, current.z)
    var distance := flat.distance_to(point)
    if distance < 0.001:
        return {"allowed": true, "clear_ahead": true}
    var direction := (point - flat).normalized()
    var travel := distance if point.distance_to(goal) < 0.05 else maxf(distance, 3.0)
    var previous := current
    var clear_m := 0.0
    for i in range(1, ceili(travel / 0.4) + 1):
        var offset := minf(float(i) * 0.4, travel)
        var next := flat + direction * offset
        var policy: Dictionary = _traversability.validate_step(previous, Vector3(next.x, previous.y, next.y), space_state)
        if not bool(policy.get("allowed", false)):
            return {"allowed": clear_m >= distance - 0.01, "clear_ahead": false, "reason": policy.get("reason", "blocked")}
        previous = policy.get("position", previous)
        clear_m = offset
    return {"allowed": true, "clear_ahead": true}
