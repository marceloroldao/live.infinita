extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:push_error(label);failures += 1
func _initialize() -> void:call_deferred("run")
func box(parent: Node3D, position: Vector3, size: Vector3) -> StaticBody3D:
    var body := StaticBody3D.new();body.position = position
    var collision := CollisionShape3D.new();var shape := BoxShape3D.new();shape.size = size;collision.shape = shape
    body.add_child(collision);parent.add_child(body);return body
func run() -> void:
    var holder := Node3D.new();root.add_child(holder)
    var ground := box(holder,Vector3(0,-0.5,0),Vector3(150,1,150))
    ground.collision_layer = 2
    var observer := CharacterBody3D.new();observer.position = Vector3(0,0.9,0);holder.add_child(observer)
    var sensor = load("res://nov_visual_perception.gd").new()
    var clock = load("res://world_map_day_cycle.gd").new()
    clock.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"test","tick":10,"tick_duration_ms":100,"logical_time_ms":1000,"cycle_ms":3600000,"paused":false})
    var manager = load("res://world_map_wildlife.gd").new();holder.add_child(manager)
    var base := "/tmp/wildlife-008ds-"+str(OS.get_process_id())
    manager.configure(true,base+".private",base+".public")
    await physics_frame;await physics_frame
    var space := holder.get_world_3d().direct_space_state
    manager.update(clock,observer,sensor,space,"test",true)
    check(manager._animals.size()==3,"Native authority spawns exactly three grounded rabbits")
    check(FileAccess.file_exists(base+".private") and FileAccess.file_exists(base+".public"),"Private checkpoint precedes renderer publication")
    check(FileAccess.get_unix_permissions(base+".private")==384 and FileAccess.get_unix_permissions(base+".public")==420,"Private state 0600 and viewer projection 0644")
    var ids: Array = []
    for rabbit in manager._animals:ids.append(rabbit.identity)
    check(ids.size()==3 and ids[0]!=ids[1],"Stable distinct animal identities")
    await physics_frame;await physics_frame
    var seen: Dictionary = sensor.scan(observer,Vector3.BACK,space,"test",1000,1.0)
    check(seen["visible_entities"].size()==3,"Animals feed eye ray sensor, not a second omniscient Nov API")
    var rabbit = manager._animals[0]
    observer.position = Vector3(40,0.9,15)
    rabbit.global_position = manager._water+Vector3.UP*0.43
    rabbit.thirst = 0.8;rabbit.hunger = 0.2
    for i in range(30):rabbit.step(0.1,manager._water,manager._food,manager._home,observer,space)
    check(rabbit.thirst<0.3 and rabbit.consumed_water==1,"Rabbit actually reaches water and completes one drink")
    rabbit.global_position = manager._food+Vector3.UP*0.43;rabbit.hunger = 0.8;rabbit.thirst = 0.2
    for i in range(30):rabbit.step(0.1,manager._water,manager._food,manager._home,observer,space)
    check(rabbit.hunger<0.3 and rabbit.consumed_food==1,"Rabbit reaches food and completes one graze")
    observer.position = rabbit.global_position+Vector3(0,0.52,4)
    check(rabbit.sees_threat(observer,space),"Rabbit can see nearby Nov")
    var wall := box(holder,rabbit.global_position+Vector3(0,0.7,2),Vector3(5,3,0.6))
    await physics_frame;await physics_frame
    check(not rabbit.sees_threat(observer,space),"Wall also blocks animal perception of Nov")
    wall.queue_free();await physics_frame;await physics_frame
    rabbit.step(0.1,manager._water,manager._food,manager._home,observer,space)
    check(rabbit.mode=="flee","Visible nearby Nov triggers programmed flight")
    observer.position = Vector3(40,0.9,15)
    rabbit.thirst = 0.9;rabbit.hunger = 0.1;rabbit.mode = "seek_water"
    var previous: Vector3 = rabbit.global_position
    var solid := box(holder,previous+Vector3(0,0,0.4),Vector3(6,3,0.3))
    await physics_frame;await physics_frame
    for i in range(20):rabbit.step(0.1,previous+Vector3(0,0,8),manager._food,manager._home,observer,space)
    check(rabbit.global_position.z<previous.z+0.30,"Physical motion cannot cross wall")
    solid.queue_free();await physics_frame;await physics_frame
    var paused := JSON.stringify(manager.snapshot(1000)["animals"])
    manager.update(clock,observer,sensor,space,"test",true)
    check(JSON.stringify(manager.snapshot(1000)["animals"])==paused,"Paused logical clock does not advance physiology or motion")
    observer.position = Vector3(100,0.9,100)
    clock._logical_ms = 1100
    manager.update(clock,observer,sensor,space,"test",true)
    check(JSON.stringify(manager.snapshot(1100)["animals"])==paused,"Leaving habitat freezes agents without moving them to follow Nov")
    check(manager.persist(1100),"Persist real current animal state")
    var saved: Dictionary = manager.snapshot(1100)
    manager.queue_free();await physics_frame;await physics_frame
    var restored = load("res://world_map_wildlife.gd").new();holder.add_child(restored)
    restored.configure(true,base+".private",base+".public")
    restored.update(clock,observer,load("res://nov_visual_perception.gd").new(),space,"test",true)
    check(JSON.stringify(restored.snapshot(1100)["animals"])==JSON.stringify(saved["animals"]),"Restart restores IDs positions needs and consumption, no respawn")
    var replica = load("res://world_map_wildlife.gd").new();holder.add_child(replica);replica.configure(false)
    check(replica.accept_replica(restored.snapshot(1100)),"Viewer accepts server physics projection")
    replica.update(clock,observer,load("res://nov_visual_perception.gd").new(),space,"test",true)
    check(replica._animals.size()==3 and JSON.stringify(replica.snapshot(1100)["animals"])==JSON.stringify(restored.snapshot(1100)["animals"]),"Viewer reproduces same population without running needs")
    var stale: Dictionary = restored.snapshot(1100);stale["generated_at_unix"]-=20
    check(not replica.accept_replica(stale),"Viewer rejects stale snapshots")
    var rewind: Dictionary = restored.snapshot(1100);rewind["sequence"]=0
    check(not replica.accept_replica(rewind),"Viewer rejects sequence rewind")
    var malformed: Dictionary = restored.snapshot(1100);malformed["animals"][0]["position"]=[99999,0,0]
    check(not replica.accept_replica(malformed),"Viewer rejects out-of-habitat positions")
    var file := FileAccess.open(base+".private",FileAccess.WRITE);file.store_string("corrupt");file.close()
    var corrupt = load("res://world_map_wildlife.gd").new();holder.add_child(corrupt);corrupt.configure(true,base+".private",base+".public")
    check(corrupt._failed and corrupt._animals.is_empty(),"Invalid checkpoint stops population instead of silently respawning")
    ground.queue_free();await physics_frame;await physics_frame
    rabbit = restored._animals[0]
    var unsupported: Vector3 = rabbit.global_position
    observer.position = Vector3(40,0.9,15)
    for i in range(10):rabbit.step(0.1,restored._water,restored._food,restored._home,observer,space)
    check(rabbit.global_position.distance_to(unsupported)<0.001,"Missing floor cannot make animals walk into unloaded holes")
    holder.queue_free();await process_frame
    for suffix in [".private",".public"]:DirAccess.remove_absolute(base+suffix)
    print("008DS_WILDLIFE_SMOKE failures=%d" % failures)
    quit(0 if failures==0 else 1)
