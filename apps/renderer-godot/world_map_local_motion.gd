extends RefCounted

const Traversability = preload("res://world_map_traversability.gd")
const NovCharacterVisual = preload("res://nov_character_visual.gd")
const SPEED_MPS := 13.0
const BODY_CENTER_Y := 0.9

var _experience = preload("res://nov_navigation_experience.gd").new()
var _traversability: RefCounted
var route_goal_id := ""
var inertial_enabled := false
var gravity_enabled := false
var terrain_response_enabled := false
var _terrain_response = preload("res://nov_terrain_response.gd").new()
var _ground_response = preload("res://nov_ground_response.gd").new()
var _locomotion = preload("res://nov_locomotion_response.gd").new()
var _journey = preload("res://nov_navigation_journey.gd").new(_experience.working_memory)
var _pattern_collector = preload("res://nov_navigation_pattern_collector.gd").new(_journey)
var _inference_log_at := 0
var _working_memory_log_at := 0
var _body_ref: WeakRef
var _episodes = preload("res://nov_navigation_episodes.gd").new()

func _init(walk_height: Callable, half_m: float = 512.0, dynamic_surface: Callable = Callable()) -> void:
    _traversability = Traversability.new(walk_height, half_m, dynamic_surface)
    _episodes.action_completed.connect(Callable(_experience.working_memory, "observe_completed"))
    _experience.contour.pattern_memory=_pattern_collector
    _episodes.action_completed.connect(Callable(_pattern_collector,"observe_action"))
    _episodes.action_completed.connect(Callable(_journey,"observe_completed"))
    _journey.attempt_finished.connect(Callable(_pattern_collector,"finish_attempt"))
    _journey.pattern_status=Callable(_pattern_collector,"status")
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
    _body_ref = weakref(body)
    return body

func snap_body(body: CharacterBody3D, ground_position: Vector3) -> void:
    body.position = ground_position + Vector3(0, BODY_CENTER_Y, 0)
    body.velocity = Vector3.ZERO
    _ground_response.reset()

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
    _traversability.max_up_step_m = _ground_response.MAX_UP_STEP_M if gravity_enabled else _traversability.MAX_STEP_M
    if gravity_enabled and _ground_response.airborne:
        return advance_gravity(current,delta,body)
    _pattern_collector.poll(Time.get_unix_time_from_system())
    if _experience.working_memory.enabled and Time.get_ticks_msec() >= _working_memory_log_at:
        _working_memory_log_at = Time.get_ticks_msec() + 30000
        print("NOV_WORKING_MEMORY_STATUS entries=%d causal_reuses=%d promoted=%d" % [_experience.working_memory.entries.size(), _experience.working_memory.causal_reuses, _experience.working_memory.promoted.size()])
    if auto_route and input_axis.length_squared()<=0.01 and _episodes.enabled and not route_goal_id.is_empty():
        commit_journey(route_goal_id,route_target,current)
        if _journey.closed:
            _locomotion.stop()
            return {"allowed":true,"position":current,"reached":true,"collisions":0,"surface":"terrain"}
    var candidate := current
    var manual := input_axis.length_squared() > 0.01
    if manual:
        candidate.x += input_axis.x * speed_mps * delta
        candidate.z += input_axis.y * speed_mps * delta
    elif auto_route:
        var flat_goal: Vector2 = _experience.target(Vector2(current.x, current.z), Vector2(route_target.x, route_target.z),
            func(point: Vector2) -> Dictionary: return _sense_ahead(current, point, space_state, Vector2(route_target.x, route_target.z)),
            func(start: Vector2, end: Vector2) -> bool:
                return _route_connection_clear(start,end,space_state))
        if Time.get_ticks_msec() >= _inference_log_at and _experience.last_decision_source == "memoria.ia":
            _inference_log_at = Time.get_ticks_msec() + 10000
            print("NOV_NAVIGATION_INFERENCE source=memoria.ia observation=%s decisions=%d anticipations=%d" % [
                _experience.last_observation_id, _experience.memory_decisions, _experience.anticipated_avoidances])
        var flat := Vector2(current.x, current.z).move_toward(flat_goal, speed_mps * delta)
        candidate.x = flat.x
        candidate.z = flat.y

    var terrain:Dictionary={}
    var effective_speed:=speed_mps
    if terrain_response_enabled:
        terrain=_terrain_response.sample(current,Vector2(candidate.x-current.x,candidate.z-current.z),Callable(_traversability,"ground_position"))
        terrain["base_speed_mps"]=speed_mps
        effective_speed=speed_mps*float(terrain.speed_factor)
        terrain["speed_limit_mps"]=effective_speed
        if not terrain.sample_valid:
            body.velocity=Vector3.ZERO
            _locomotion.stop()
            terrain["actual_speed_mps"]=0.0
            _journey.terrain_motion=terrain
            _journey.save_status()
            return {"allowed":false,"position":current,"reason":"terrain_sample_unavailable","collisions":0,"reached":false,"terrain_motion":terrain}
        if not inertial_enabled:
            candidate=current+(candidate-current)*float(terrain.speed_factor)
    if inertial_enabled:
        var move: Vector2 = _locomotion.displacement(Vector2(current.x,current.z),Vector2(candidate.x,candidate.z),Vector2(route_target.x,route_target.z) if auto_route and not manual else Vector2(current.x,current.z)+input_axis*100.0,effective_speed,delta)
        candidate = current+Vector3(move.x,0,move.y)
    var policy: Dictionary = _traversability.validate_step(current, candidate, space_state)
    if _episodes.enabled:
        if not bool(policy.get("allowed",false)) or _experience.last_decision_source=="perception-no-passage":
            _journey.motion_state = "no_passage"
            _journey.last_reason = str(policy.get("reason",""))
        else:
            _journey.motion_state = "water_egress" if bool(policy.get("environment_escape",false)) else "walking"
            _journey.last_reason = ""
        # Terrain diagnostics are published after physical execution.
        if not terrain_response_enabled:_journey.save_status()
    if terrain_response_enabled:
        terrain["actual_speed_mps"]=0.0
        policy["terrain_motion"]=terrain
        _journey.terrain_motion=terrain
    policy["route_goal_id"] = route_goal_id
    if _experience._route_search.running and not manual:
        policy["reason"] = "route_search_in_progress"
    policy["manual"] = manual
    policy["decision_source"] = _experience.last_decision_source
    policy["memory_observation_id"] = _experience.last_observation_id
    policy["working_memory_session"] = _experience.working_memory.session
    policy["working_memory_key"] = _experience.working_memory_key
    policy["working_memory_changed_choice"] = _experience.working_memory_changed_choice
    if gravity_enabled and bool(policy.get("allowed",false)) and float(policy.get("position",current).y)-current.y>_ground_response.MAX_UP_STEP_M:
        policy["allowed"]=false
        policy["position"]=current
        policy["reason"]="step_too_high"
    if not bool(policy.get("allowed", false)):
        if terrain_response_enabled:_journey.save_status()
        if auto_route and not manual:
            _experience.blocked()
        policy["reached"] = false
        body.velocity = Vector3.ZERO
        _locomotion.stop()
        if auto_route and not manual:
            _episodes.observe(_experience.decision_serial, current, route_target, _experience.pending, _experience.decision_evidence, policy)
        return policy

    var target: Vector3 = policy.get("position", current)
    body.position = current+Vector3(0,BODY_CENTER_Y,0)
    body.velocity = Vector3.ZERO
    var displacement := Vector3(target.x - current.x, 0, target.z - current.z)
    # Swept motion uses the requested dt even in presentation smoke calls.
    body.move_and_collide(displacement)
    policy["executed_motion"] = true

    var resolved: Vector3 = _traversability.ground_position(body.position.x, body.position.z)
    var vertical:Dictionary={}
    if gravity_enabled:
        var horizontal_m:=Vector2(resolved.x-current.x,resolved.z-current.z).length()
        var follow_slope:=horizontal_m>0.001 and absf(resolved.y-current.y)/horizontal_m<=0.7
        vertical=_apply_vertical(Vector3(resolved.x,current.y,resolved.z),resolved.y,delta,body,follow_slope)
        resolved=vertical.position
        policy["grounded"]=vertical.grounded
        policy["vertical_speed_mps"]=vertical.vertical_speed_mps
        policy["gravity_enabled"]=true
        if not vertical.grounded:_locomotion.stop()
    else:
        body.position.y = resolved.y + BODY_CENTER_Y
    var collisions := 1 if Vector2(resolved.x - target.x, resolved.z - target.z).length() > 0.02 else 0
    if inertial_enabled:
        _locomotion.executed(Vector2(resolved.x-current.x,resolved.z-current.z),delta,collisions>0 or (gravity_enabled and _ground_response.airborne))
        body.velocity = Vector3(_locomotion.velocity.x,_ground_response.vertical_speed if gravity_enabled else 0.0,_locomotion.velocity.y)
        policy["physical_speed_mps"] = _locomotion.velocity.length()
        policy["inertial_motion"] = true
    if terrain_response_enabled:
        terrain["actual_speed_mps"]=Vector2(resolved.x-current.x,resolved.z-current.z).length()/maxf(delta,0.001)
        _journey.terrain_motion=terrain
        _journey.save_status()
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
        (not gravity_enabled or not _ground_response.airborne)
        and auto_route
        and not manual
        and Vector2(resolved.x, resolved.z).distance_to(Vector2(route_target.x, route_target.z)) < 0.1
    )
    if auto_route and not manual:
        _journey.movement(current,resolved)
        _episodes.observe(_experience.decision_serial, current, route_target, _experience.pending, _experience.decision_evidence, policy)
    return policy

func _sense_ahead(current: Vector3, point: Vector2, space_state: PhysicsDirectSpaceState3D, goal: Vector2) -> Dictionary:
    var flat := Vector2(current.x, current.z)
    var distance := flat.distance_to(point)
    if distance < 0.001:
        return {"allowed": true, "clear_ahead": true}
    # The proposed metre must pass the same whole-step check as execution.
    # Short look-ahead samples alone can conceal an excessive total rise.
    var proposed: Dictionary = _traversability.validate_step(current, Vector3(point.x,current.y,point.y), space_state)
    if not bool(proposed.get("allowed",false)):
        return {"allowed":false,"clear_ahead":false,"reason":proposed.get("reason","blocked")}
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

func _route_connection_clear(start: Vector2, end: Vector2, space_state: PhysicsDirectSpaceState3D) -> bool:
    # A graph edge is two metres; actual decisions advance at most one metre.
    var previous: Vector3 = _traversability.ground_position(start.x,start.y)
    var flat := start
    while flat.distance_to(end)>0.001:
        flat = flat.move_toward(end,1.0)
        var policy: Dictionary = _traversability.validate_step(previous,Vector3(flat.x,previous.y,flat.y),space_state)
        if not bool(policy.get("allowed",false)): return false
        previous = policy.get("position",previous)
    return true

func resolve_destination(requested: Vector3) -> Dictionary:
    # Resolve only the local presentation destination; the feed remains unchanged.
    var space: PhysicsDirectSpaceState3D = null
    if _body_ref!=null:
        var body = _body_ref.get_ref()
        if is_instance_valid(body) and body.is_inside_tree():
            space = body.get_world_3d().direct_space_state
    var ground: Vector3 = _traversability.ground_position(requested.x,requested.z)
    if _destination_clear(ground,space):
        return {"allowed":true,"position":requested,"adjusted":false}
    for radius in range(1,17):
        for heading in range(16):
            var offset := Vector2.RIGHT.rotated(TAU*float(heading)/16.0)*float(radius)
            var candidate: Vector3 = _traversability.ground_position(requested.x+offset.x,requested.z+offset.y)
            if _destination_clear(candidate,space):
                return {"allowed":true,"position":candidate,"adjusted":true}
    return {"allowed":false,"reason":"no_walkable_destination_within_16m"}


func _destination_clear(ground: Vector3, space: PhysicsDirectSpaceState3D) -> bool:
    # A zero-length step checks the full body at the endpoint without
    # interpreting a blocked approach corridor as an occupied destination.
    return bool(_traversability.validate_step(ground,ground,space).get("allowed",false))

func commit_journey(identity: String, target: Vector3, current: Vector3) -> void:
    if not _episodes.enabled:return
    if identity.is_empty():
        if not _journey.closed:
            _journey.abort("objetivo encerrado","goal_ended")
            if not _episodes.active.is_empty():
                _episodes._finish("interrupted",current,Time.get_ticks_msec(),"journey_goal_ended")
        return
    var changed: bool = _journey.begin(identity,Vector2(target.x,target.z),str(_episodes.context.get("world_id","")),Vector2(current.x,current.z))
    if changed and not _episodes.active.is_empty():
        _episodes._finish("interrupted",current,Time.get_ticks_msec(),"journey_goal_changed")


func resolve_recovery_start(requested: Vector3, space: PhysicsDirectSpaceState3D) -> Dictionary:
    # Arrival and at least one two-metre exit must be physically clear.
    # Bounded local search around the original start; never enter water.
    if not requested.is_finite():
        return {"allowed":false,"reason":"invalid_recovery_origin"}
    for radius in [0.0,4.0,8.0,12.0,16.0,24.0,32.0]:
        for heading in range(1 if radius==0.0 else 12):
            var offset := Vector2.RIGHT.rotated(TAU*float(heading)/12.0)*float(radius)
            var candidate: Vector3 = _traversability.ground_position(requested.x+offset.x,requested.z+offset.y)
            if not candidate.is_finite() or not _destination_clear(candidate,space):
                continue
            for escape_heading in range(8):
                var direction := Vector2.RIGHT.rotated(TAU*float(escape_heading)/8.0)
                var first := candidate+Vector3(direction.x,0,direction.y)
                var step: Dictionary = _traversability.validate_step(candidate,first,space)
                if not bool(step.get("allowed",false)):continue
                var second: Vector3 = step["position"]+Vector3(direction.x,0,direction.y)
                if bool(_traversability.validate_step(step["position"],second,space).get("allowed",false)):
                    return {"allowed":true,"position":candidate}
    return {"allowed":false,"reason":"no_safe_recovery_start"}

func recover_to(current: Vector3, destination: Vector3, body: CharacterBody3D, space: PhysicsDirectSpaceState3D) -> bool:
    if not destination.is_finite() or not _destination_clear(destination,space):
        return false
    if _episodes.enabled:
        if not _episodes.active.is_empty():
            _episodes._finish("interrupted",current,Time.get_ticks_msec(),"stuck_recovery")
        _journey.abort("preso; retorno ao início","stuck_recovery")
        _journey.recoveries += 1
        _journey.save_status(true)
    _experience.active = false
    _experience.reset_route_plan()
    _experience.visits.clear()
    route_goal_id = ""
    _locomotion.stop()
    snap_body(body,destination)
    print("NOV_STUCK_RECOVERY from=(%.1f,%.1f) to=(%.1f,%.1f)" % [current.x,current.z,destination.x,destination.z])
    return true

func abort_journey(reason: String, termination: String) -> void:
    _journey.abort(reason,termination)

func approach_context(current: Vector3, observed: Vector3, logical_ms: int) -> Dictionary:
    if _body_ref==null or logical_ms<0 or not current.is_finite() or not observed.is_finite():return {}
    var body=_body_ref.get_ref()
    if not is_instance_valid(body) or not body.is_inside_tree():return {}
    var direction:=Vector3(observed.x-current.x,0,observed.z-current.z)
    if direction.length_squared()<0.0001:return {}
    var pose:Transform3D=body.global_transform
    pose.origin=current+Vector3(0,BODY_CENTER_Y,0)
    return {"profile":"capsule044-height18-sweep4-native-contour-v1","sweep_m":4.0,
        "blocked_ahead":body.test_move(pose,direction.normalized()*4.0),"sample_logical_ms":logical_ms}

func _apply_vertical(current:Vector3,ground:float,dt:float,body:CharacterBody3D,follow_surface:bool=false)->Dictionary:
    var next:Dictionary=_ground_response.advance(current.y,ground,dt,follow_surface)
    body.position=current+Vector3(0,BODY_CENTER_Y,0)
    var collision=body.move_and_collide(Vector3(0,float(next.height)-current.y,0))
    var actual:=body.position-Vector3(0,BODY_CENTER_Y,0)
    if collision!=null:
        _ground_response.reset()
    body.velocity.y=_ground_response.vertical_speed
    return {"position":actual,"grounded":not _ground_response.airborne,"vertical_speed_mps":_ground_response.vertical_speed,"collisions":1 if collision!=null else 0}

func advance_gravity(current:Vector3,dt:float,body:CharacterBody3D)->Dictionary:
    _locomotion.stop()
    var ground:Vector3=_traversability.ground_position(current.x,current.z)
    var result:Dictionary=_apply_vertical(current,ground.y,dt,body)
    result["allowed"]=true
    result["gravity_enabled"]=true
    result["executed_motion"]=true
    result["surface"]="terrain" if result.grounded else "airborne"
    result["reason"]=""
    result["reached"]=false
    result["decision_source"]="local_physics_gravity"
    if terrain_response_enabled:
        _journey.terrain_motion={"enabled":true,"phase":"airborne" if not result.grounded else "landed","actual_speed_mps":0.0,"speed_limit_mps":0.0,"source":"local_physics_gravity","world_write_authority":false}
        result["terrain_motion"]=_journey.terrain_motion
    if _episodes.enabled:
        _journey.motion_state="walking" if result.grounded else "falling"
        _journey.save_status()
    return result
