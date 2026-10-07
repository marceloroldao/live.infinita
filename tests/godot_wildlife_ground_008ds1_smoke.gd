extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures += 1
func _initialize() -> void:call_deferred("run")
func run() -> void:
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage);stage.set_process(false);stage.set_physics_process(false)
    await physics_frame;await physics_frame
    var space: PhysicsDirectSpaceState3D = stage.get_world_3d().direct_space_state
    var position: Vector3 = stage._position
    var ray := PhysicsRayQueryParameters3D.create(position+Vector3.UP*20,position-Vector3.UP*30,2)
    var hit := space.intersect_ray(ray)
    check(not hit.is_empty(),"Actual preview ground has physical support without artificial test floor")
    if not hit.is_empty():
        check(absf(hit["position"].y-stage._height(position.x,position.z))<0.001,"Collider height is identical to resident visible triangles")
        check(hit["normal"].y>0.8,"Terrain face winding points upward")
    check(stage._walker.collision_mask==1,"Nov retains previous analytical locomotion and obstacle mask")
    var wildlife = stage._wildlife
    wildlife.configure(true)
    stage._day_cycle.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"fixture","tick":10,"tick_duration_ms":100,"logical_time_ms":1000,"cycle_ms":3600000,"paused":false})
    wildlife.update(stage._day_cycle,stage._walker,stage._visual_perception,space,"fixture",true)
    check(wildlife._animals.size()==3,"Three animals spawn on actual preview map")
    for animal in wildlife._animals:
        check(not animal.support(animal.global_position,space,[animal.get_rid()]).is_empty(),"Each spawned animal has actual terrain support")
    var starts: Array = []
    for animal in wildlife._animals:starts.append(animal.global_position)
    for i in range(60):
        stage._day_cycle._logical_ms += 50.0
        wildlife.update(stage._day_cycle,stage._walker,stage._visual_perception,space,"fixture",true)
    var moved := 0
    for i in range(wildlife._animals.size()):
        if wildlife._animals[i].global_position.distance_to(starts[i])>0.2:moved += 1
    check(moved>=1,"Real-ground capsules must move, not remain stuck against slope")
    # The fixed fixture records no episodes; only synthetic habitat is created.
    stage.queue_free();await process_frame
    print("008DS1_REAL_GROUND_SMOKE failures=%d" % failures)
    quit(0 if failures==0 else 1)
