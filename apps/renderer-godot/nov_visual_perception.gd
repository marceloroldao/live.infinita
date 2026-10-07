extends RefCounted
# Candidate transforms stay private; only ray-confirmed sightings leave the sensor.
signal observation_ready(observation: Dictionary)
const MAX_TARGETS := 128
const MAX_RAYS := 16
const DAY_RANGE_M := 24.0
const NIGHT_RANGE_M := 12.0
const HORIZONTAL_FOV_DEG := 120.0
const VERTICAL_FOV_DEG := 80.0
# Nov's CharacterBody origin is 0.9 m above its feet; eyes are at 1.55 m.
const EYE_ABOVE_BODY_M := 0.65
var _targets: Dictionary = {}
var _world := ""
var _last_logical_ms := -1
var _cursor := 0
var _latest: Dictionary = {}
var _last_ray_count := 0

func register_target(node: Node3D, identity: String, kind: String, world: String, aim_offset: Vector3 = Vector3(0,0.6,0)) -> bool:
    if not is_instance_valid(node) or identity.is_empty() or identity.length()>160 or world.is_empty() or world.length()>160 or kind.is_empty() or kind.length()>40 or not aim_offset.is_finite() or aim_offset.length()>4.0:
        return false
    for old_key in _targets.keys():
        var old_node = _targets[old_key]["node"].get_ref()
        if not is_instance_valid(old_node) or old_node.is_queued_for_deletion():
            _targets.erase(old_key)
    var key := JSON.stringify([world,identity])
    if _targets.has(key):
        var existing = _targets[key]["node"].get_ref()
        if is_instance_valid(existing) and existing != node:
            return false
    elif _targets.size() >= MAX_TARGETS:
        return false
    _targets[key] = {"node":weakref(node),"id":identity,"kind":kind,"world":world,"aim_offset":aim_offset}
    return true

func unregister_target(identity: String, world: String) -> void:
    _targets.erase(JSON.stringify([world,identity]))

func clear_observation() -> void:
    _latest = {}
    _last_ray_count = 0

func latest() -> Dictionary:
    return _latest.duplicate(true)

func scan(observer: CharacterBody3D, forward: Vector3, space: PhysicsDirectSpaceState3D, world: String, logical_ms: int, daylight: float) -> Dictionary:
    clear_observation()
    if not is_instance_valid(observer) or not observer.is_inside_tree() or space == null or world.is_empty() or logical_ms<0 or not forward.is_finite() or not is_finite(daylight):
        return {}
    var heading := Vector3(forward.x,0,forward.z)
    if heading.length_squared()<0.0001:
        return {}
    if world != _world:
        _world = world
        _last_logical_ms = -1
        _cursor = 0
    if logical_ms < _last_logical_ms:
        return {}
    _last_logical_ms = logical_ms
    heading = heading.normalized()
    var eye := observer.global_position+Vector3.UP*EYE_ABOVE_BODY_M
    if not eye.is_finite():
        return {}
    var reach := lerpf(NIGHT_RANGE_M,DAY_RANGE_M,clampf(daylight,0,1))
    var eligible: Array = []
    for key in _targets.keys():
        var item: Dictionary = _targets[key]
        var node = item["node"].get_ref()
        if not is_instance_valid(node) or node.is_queued_for_deletion():
            _targets.erase(key)
            continue
        if item["world"] != world or node == observer or not node.is_inside_tree() or not node.is_visible_in_tree():
            continue
        var aim: Vector3 = node.to_global(item["aim_offset"])
        var relative := aim-eye
        var distance := relative.length()
        if not aim.is_finite() or distance<0.05 or distance>reach:
            continue
        var flat := Vector3(relative.x,0,relative.z)
        if flat.length_squared()<0.0001 or heading.dot(flat.normalized())<cos(deg_to_rad(HORIZONTAL_FOV_DEG*0.5)):
            continue
        if absf(relative.y)/distance>sin(deg_to_rad(VERTICAL_FOV_DEG*0.5)):
            continue
        eligible.append({"item":item,"node":node,"aim":aim,"distance":distance})
    var sightings: Array = []
    var count := mini(MAX_RAYS,eligible.size())
    for i in range(count):
        var candidate: Dictionary = eligible[(_cursor+i)%eligible.size()]
        var query := PhysicsRayQueryParameters3D.create(eye,candidate["aim"],1,[observer.get_rid()])
        query.collide_with_areas = false
        query.hit_from_inside = true
        var hit := space.intersect_ray(query)
        _last_ray_count += 1
        var visible := hit.is_empty()
        if not visible:
            var collider = hit.get("collider")
            visible = collider == candidate["node"] or (collider is Node and candidate["node"].is_ancestor_of(collider))
        if visible:
            var item: Dictionary = candidate["item"]
            var position: Vector3 = candidate["aim"]
            sightings.append({"entity_id":item["id"],"kind":item["kind"],
                "observed_position_m":[position.x,position.y,position.z],"distance_m":candidate["distance"],
                "evidence":"eye_ray_unobstructed"})
    if not eligible.is_empty():
        _cursor = (_cursor+count)%eligible.size()
    _latest = {"schema":"live-infinita-nov-visual-observation/v1","world_id":world,
        "observer_entity_id":"nov","logical_time_ms":logical_ms,"observed_monotonic_ms":Time.get_ticks_msec(),"source":"local_physics_eye_sensor",
        "coordinate_space":"godot-renderer-xz-metres","eye_position_m":[eye.x,eye.y,eye.z],
        "forward":[heading.x,heading.y,heading.z],"range_m":reach,"horizontal_fov_deg":HORIZONTAL_FOV_DEG,
        "visible_entities":sightings,"absence_claim":false,"world_write_authority":false}
    observation_ready.emit(latest())
    return latest()
