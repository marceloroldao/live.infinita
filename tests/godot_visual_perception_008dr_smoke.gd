extends SceneTree
class FakeEpisodes:
    extends RefCounted
    var context := {"world_id":"test"}
class FakeMotion:
    extends RefCounted
    var _episodes = FakeEpisodes.new()
class PerceptionPreview:
    extends "res://world_map_preview.gd"
    func _ready() -> void:pass
    func _process(_delta: float) -> void:pass
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func ids(observation: Dictionary) -> Array:
    var result: Array = []
    for row in observation.get("visible_entities",[]):result.append(row["entity_id"])
    return result
func block(parent: Node3D, position: Vector3, size: Vector3) -> StaticBody3D:
    var body := StaticBody3D.new()
    body.position = position
    body.collision_layer = 1
    var collision := CollisionShape3D.new()
    var shape := BoxShape3D.new()
    shape.size = size
    collision.shape = shape
    body.add_child(collision)
    parent.add_child(body)
    return body
func target(parent: Node3D, position: Vector3) -> Node3D:
    var node := Node3D.new()
    node.position = position
    parent.add_child(node)
    return node
func run() -> void:
    var sensor = load("res://nov_visual_perception.gd").new()
    var holder := Node3D.new()
    root.add_child(holder)
    var observer := CharacterBody3D.new()
    observer.position = Vector3(0,0.9,0)
    holder.add_child(observer)
    var near := target(holder,Vector3(0,0,10))
    var far := target(holder,Vector3(0,0,30))
    var behind := target(holder,Vector3(0,0,-8))
    var side := target(holder,Vector3(8,0,0))
    var alien := target(holder,Vector3(2,0,8))
    var high := target(holder,Vector3(0,15,5))
    check(sensor.register_target(near,"near","animal-test","test"),"Register near physical fixture")
    sensor.register_target(far,"far","animal-test","test")
    sensor.register_target(behind,"behind","animal-test","test")
    sensor.register_target(side,"side","animal-test","test")
    sensor.register_target(alien,"foreign-world","animal-test","other")
    sensor.register_target(high,"overhead","animal-test","test")
    await physics_frame
    var space := holder.get_world_3d().direct_space_state
    var seen: Dictionary = sensor.scan(observer,Vector3.BACK,space,"test",1000,1.0)
    check(ids(seen)==["near"],"Only in-range forward target is visible")
    check(not JSON.stringify(seen).contains("foreign-world") and not JSON.stringify(seen).contains("behind"),"Hidden identities never leave sensor")
    check(absf(float(seen["eye_position_m"][1])-1.55)<0.0001,"Eye is measured from feet, not camera")
    check(seen["absence_claim"]==false,"Empty cone is not absence of animals everywhere")
    var wall := block(holder,Vector3(0,1.5,5),Vector3(4,3,1))
    await physics_frame
    seen = sensor.scan(observer,Vector3.BACK,space,"test",1100,1.0)
    check(ids(seen).is_empty(),"Physical wall occludes target")
    check(not JSON.stringify(seen).contains('"near"'),"Occluded target coordinates and identity are not reported")
    wall.queue_free()
    await physics_frame
    await physics_frame
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1200,1.0))==["near"],"Target reappears only after physical wall removal")
    var trunk := StaticBody3D.new()
    trunk.position = Vector3(0,1.5,5)
    var shape := CylinderShape3D.new()
    shape.radius = 0.45;shape.height = 3.0
    var collision := CollisionShape3D.new();collision.shape = shape;trunk.add_child(collision);holder.add_child(trunk)
    await physics_frame
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1300,1.0)).is_empty(),"Solid tree trunk occludes sight")
    trunk.queue_free();await physics_frame;await physics_frame
    near.position.z = 18
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1400,1.0))==["near"],"Day allows target eighteen metres away")
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1500,0.0)).is_empty(),"Night reduces range to twelve metres")
    near.visible = false
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1600,1.0)).is_empty(),"Unmaterialized invisible target cannot create sighting")
    near.visible = true
    check(sensor.scan(observer,Vector3.BACK,space,"test",1000,1.0).is_empty() and sensor.latest().is_empty(),"Clock rewind does not retain stale sightings")
    var visible_body := block(holder,Vector3(0,0.6,6),Vector3(1,1.2,1))
    sensor.register_target(visible_body,"physical-target","animal-test","test",Vector3.ZERO)
    await physics_frame
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1700,1.0)).has("physical-target"),"Hitting target's own collider confirms visibility")
    var saved: Dictionary = sensor.latest();saved["visible_entities"].clear()
    check(not ids(sensor.latest()).is_empty(),"Consumer cannot mutate sensor observation")
    sensor.unregister_target("physical-target","test")
    visible_body.queue_free();await physics_frame;await physics_frame
    near.queue_free();await physics_frame;await physics_frame
    check(ids(sensor.scan(observer,Vector3.BACK,space,"test",1800,1.0)).is_empty(),"Freed targets disappear without stale coordinates")
    var budget = load("res://nov_visual_perception.gd").new()
    for i in range(24):
        budget.register_target(target(holder,Vector3(float(i)*0.01,0,8)),"budget-"+str(i),"animal-test","test")
    var all_ids: Dictionary = {}
    for i in range(2):
        var observation: Dictionary = budget.scan(observer,Vector3.BACK,space,"test",2000+i,1.0)
        check(budget._last_ray_count<=16,"Raycast work is bounded per scan")
        for identity in ids(observation):all_ids[identity]=true
    check(all_ids.size()==24,"Round robin does not permanently starve candidates")
    for i in range(24,128):
        budget.register_target(target(holder,Vector3(0,0,40)),"budget-"+str(i),"animal-test","test")
    check(not budget.register_target(target(holder,Vector3(0,0,8)),"overflow","animal-test","test"),"Registry is bounded at 128")
    var preview := PerceptionPreview.new()
    root.add_child(preview)
    preview.set_physics_process(false)
    preview._live_authoritative = true
    preview._live_last_update_ms = Time.get_ticks_msec()
    preview._walker = observer
    preview._local_motion = FakeMotion.new()
    var fixture := target(holder,Vector3(0,0,8))
    check(preview.register_perception_target(fixture,"integrated","animal-test","test"),"Preview exposes explicit target registration")
    preview._day_cycle.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"test","tick":3600,"tick_duration_ms":500,"logical_time_ms":1800000,"cycle_ms":3600000,"paused":false})
    preview._physics_process(0.1)
    check(preview._visual_perception.latest().is_empty(),"Preview samples at bounded four hertz")
    preview._physics_process(0.15)
    check(ids(preview._visual_perception.latest())==["integrated"],"Native/browser preview integration uses physical eye sensor")
    preview._recovery_pending = true
    preview._physics_process(0.25)
    check(preview._visual_perception.latest().is_empty(),"Recovery clears stale sightings")
    preview._recovery_pending = false
    preview._local_motion._episodes.context["world_id"] = "wrong"
    preview._physics_process(0.25)
    check(preview._visual_perception.latest().is_empty(),"Clock/world mismatch does not publish observation")
    preview._local_motion._episodes.context["world_id"] = "test"
    preview._live_last_update_ms = Time.get_ticks_msec()-11000
    preview._physics_process(0.25)
    check(preview._visual_perception.latest().is_empty(),"Stale feed cannot stamp sightings as fresh authoritative observations")
    preview.queue_free()
    holder.queue_free()
    await process_frame
    print("008DR_VISUAL_PERCEPTION_SMOKE failures=%d" % failures)
    quit(0 if failures==0 else 1)
