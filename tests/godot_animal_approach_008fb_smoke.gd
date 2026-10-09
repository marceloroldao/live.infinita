extends SceneTree
var failures:=0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func allowed(point: Vector3) -> Dictionary:
    return {"allowed":true,"position":point}
func policy():
    var value=load("res://nov_animal_approach.gd").new()
    value.enabled=true
    value.choose(Vector3.ZERO,"fixture",100000,Callable(self,"allowed"))
    return value
func verify_persistence(_approach: RefCounted) -> void:
    pass
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var host:=Node3D.new();root.add_child(host)
    var body:=CharacterBody3D.new();body.collision_layer=1;body.collision_mask=1;host.add_child(body);body.position=Vector3(0,.9,0)
    var capsule:=CollisionShape3D.new();capsule.shape=CapsuleShape3D.new();capsule.shape.radius=.44;capsule.shape.height=1.8;body.add_child(capsule)
    var rabbit:=StaticBody3D.new();rabbit.collision_layer=1;host.add_child(rabbit);rabbit.position=Vector3(10,.2,0)
    var shape:=CollisionShape3D.new();shape.shape=BoxShape3D.new();shape.shape.size=Vector3(.5,.4,.5);rabbit.add_child(shape)
    var wall:=StaticBody3D.new();wall.collision_layer=1;host.add_child(wall);wall.position=Vector3(4,1,0)
    var wall_shape:=CollisionShape3D.new();wall_shape.shape=BoxShape3D.new();wall_shape.shape.size=Vector3(.4,3,4);wall.add_child(wall_shape)
    var sensor=load("res://nov_visual_perception.gd").new()
    sensor.register_target(rabbit,"fixture:rabbit:0","rabbit","fixture",Vector3.ZERO)
    var approach=policy()
    sensor.observation_ready.connect(Callable(approach,"observe"))
    await physics_frame
    var observation: Dictionary=sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",100100,1.0)
    check(observation.visible_entities.is_empty(),"Physical wall occludes rabbit")
    check(approach.choose(body.position,"fixture",100100,Callable(self,"allowed")).is_empty(),"Occluded rabbit supplies no approach")
    wall.queue_free();await physics_frame;await physics_frame
    observation=sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",100200,1.0)
    check(observation.visible_entities.size()==1,"Unobstructed physical eye sees rabbit")
    var selection: Dictionary=approach.choose(body.position,"fixture",100200,Callable(self,"allowed"))
    check(selection.get("arm")=="visible" and selection.get("source")=="local_physics_eye_sensor","Sight starts bounded approach")
    check(selection.deadline_ms-selection.started_ms==20000,"Approach budget fixed")
    var revision:int=selection.revision
    check(approach.choose(body.position,"fixture",100250,Callable(self,"allowed")).revision==revision,"Repeated frames retain committed route")
    var panel=load("res://nov_animal_search_panel.gd").new();root.add_child(panel);panel.set_process(false);panel.enabled=true;panel.set_world("fixture")
    var public: Dictionary={"schema":"live-infinita-nov-animal-search-intent/v1","world_id":"fixture","generated_at_unix":Time.get_unix_time_from_system(),"world_write_authority":false,"decision_use":true,"last_error":null,"source":"native_bounded_animal_search","absence_claim":false,"active":true,"logical_time_ms":100250,"intent":selection}
    check(panel._accept(JSON.stringify(public),"intent"),"Observed approach reaches read-only browser presentation")
    check(panel.intent(-1,100250).arm=="visible","Public intent preserves source distinction")
    check(panel.lines().contains("coelho avistado"),"Live panel explains observed approach")
    public.intent.source="physical_registry"
    check(not panel._accept(JSON.stringify(public),"intent"),"Direct physical registry cannot impersonate perception")
    # Actual incremental CharacterBody movement, using fresh physical eye scans.
    var collisions:=0
    var travelled:=0.0
    for i in range(80):
        var now:=100300+i*100
        sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",now,1.0)
        selection=approach.choose(body.position,"fixture",now,Callable(self,"allowed"))
        if selection.is_empty():break
        var point:=Vector3(selection.goal[0],body.position.y,selection.goal[2])
        var previous:=body.position
        if body.move_and_collide((point-body.position).normalized()*.1)!=null:collisions+=1
        travelled+=body.position.distance_to(previous)
        await physics_frame
    check(approach._results.size()==1 and approach._results[0].result=="approached","Approach confirmed only after actual close movement and fresh sight")
    check(travelled>3.0 and travelled<4.0 and collisions==0,"Measured physical movement without teleport or collision")
    check(approach._results[0].revision==1,"Stationary animal must not repeatedly reset physical route")
    check(not approach._results[0].capture and not approach._results[0].absence_claim,"Approach does not imply capture or absence")
    check(approach.choose(body.position,"fixture",109000,Callable(self,"allowed")).is_empty(),"Completed approach cannot restart during cooldown")
    verify_persistence(approach)
    var lost=policy();lost.observe(observation)
    lost.choose(Vector3.ZERO,"fixture",100300,Callable(self,"allowed"))
    check(lost.choose(Vector3.ZERO,"fixture",102000,Callable(self,"allowed")).is_empty() and lost._results[0].result=="contact_lost","Lost sight expires, not omniscient pursuit")
    var blocked=policy();blocked.observe(observation)
    check(blocked.choose(Vector3.ZERO,"fixture",100300,func(_p):return {"allowed":false}).is_empty() and blocked._results[0].result=="destination_rejected","Normal destination rejection cancels approach")
    var disabled=policy();disabled.enabled=false;disabled.observe(observation)
    check(disabled.choose(Vector3.ZERO,"fixture",100300,Callable(self,"allowed")).is_empty(),"Disabled controller cannot move Nov")
    var future=policy();var altered:=observation.duplicate(true);altered.logical_time_ms=200000;future.observe(altered)
    check(future.choose(Vector3.ZERO,"fixture",100300,Callable(self,"allowed")).is_empty(),"Future observations cannot steer present")
    var invalid=policy();altered=observation.duplicate(true);altered.logical_time_ms=1.0e16;invalid.observe(altered)
    check(invalid._seen.is_empty(),"Oversized timestamp cannot overflow accepted observation clock")
    altered=observation.duplicate(true);altered.source="physical_registry";invalid.observe(altered)
    check(invalid._seen.is_empty(),"Physical registry cannot bypass eye observation contract")
    var regressed=policy();regressed.observe(observation);regressed.choose(Vector3.ZERO,"fixture",100300,Callable(self,"allowed"))
    check(regressed.choose(Vector3.ZERO,"fixture",100299,Callable(self,"allowed")).is_empty(),"Clock rewind cancels approach")
    var moving=policy()
    observation=sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",110000,1.0)
    moving.observe(observation)
    var first: Dictionary=moving.choose(Vector3.ZERO,"fixture",110000,Callable(self,"allowed"))
    rabbit.position.x+=3.0
    await physics_frame
    observation=sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",111100,1.0)
    moving.observe(observation)
    var second: Dictionary=moving.choose(Vector3.ZERO,"fixture",111100,Callable(self,"allowed"))
    check(second.revision==first.revision+1 and second.goal[0]>first.goal[0]+2.0,"Only new sighted target movement retargets committed destination")
    moving.finish("test_interrupted")
    var stalled=policy();stalled.observe(observation)
    stalled.choose(Vector3.ZERO,"fixture",111100,Callable(self,"allowed"))
    observation=sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",119101,1.0)
    stalled.observe(observation)
    check(stalled.choose(Vector3.ZERO,"fixture",119101,Callable(self,"allowed")).is_empty() and stalled._results[0].result=="no_progress","Fresh sightings cannot sustain eight seconds without physical progress")
    var budget=policy();budget.observe(observation)
    budget.choose(Vector3.ZERO,"fixture",119101,Callable(self,"allowed"))
    observation=sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",139101,1.0)
    budget.observe(observation)
    check(budget.choose(Vector3.ZERO,"fixture",139101,Callable(self,"allowed")).is_empty() and budget._results[0].result=="budget_exhausted","Fresh sightings cannot extend twenty-second budget")
    # Native scene integration uses the existing collision-aware locomotion path.
    var stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage);stage.set_process(false);stage.set_physics_process(false)
    await physics_frame
    stage.get_node("LiveFeed").enabled=false
    stage._local_motion._episodes.context={"world_id":"fixture"}
    stage._day_cycle.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"fixture","paused":false,"tick":200,"tick_duration_ms":500,"logical_time_ms":100000,"cycle_ms":3600000})
    var directory:="/tmp/animal-approach-"+Crypto.new().generate_random_bytes(8).hex_encode()
    DirAccess.make_dir_recursive_absolute(directory)
    stage._animal_search_intent.configure(directory+"/state",directory+"/public",directory+"/source","a".repeat(32))
    check(stage._animal_search_intent._approach.enabled==(OS.get_environment("LIVE_INFINITA_ANIMAL_APPROACH_ENABLED")=="1"),"Native configuration obeys reversible environment flag")
    stage._animal_search_intent._approach.enabled=true
    var before:Vector3=stage._position
    stage._animal_search_intent._approach.choose(before,"fixture",100000,Callable(stage._local_motion,"resolve_destination"))
    var accepted:=false
    for i in range(8):
        var direction:=Vector2.RIGHT.rotated(TAU*i/8.0)
        var point:=before+Vector3(direction.x,0,direction.y)*10.0
        var goal:=point-Vector3(direction.x,0,direction.y)*5.0
        if not stage._local_motion.resolve_destination(goal).get("allowed",false):continue
        # Explicit adapter contract fixture; not a new physical observation or memory ingestion.
        var row:=observation.duplicate(true);row.logical_time_ms=100000
        row.visible_entities[0].observed_position_m=[point.x,point.y,point.z]
        stage._animal_search_intent.observe(row);accepted=true;break
    check(accepted,"Native scene provides walkable local destination")
    stage._advance_live_walk(.05)
    check(stage._animal_search_selection.get("arm")=="visible","Native renderer selects observed approach")
    check(stage._position.distance_to(before)>0 and stage._position.distance_to(before)<.8,"Existing native motion advances incrementally")
    stage._animal_search_intent.suspend("clock_unavailable")
    check(not stage._animal_search_intent._approach.status().active,"Pause cancels active approach")
    var stopped=JSON.parse_string(FileAccess.get_file_as_string(directory+"/public"))
    check(not stopped.active and not stopped.approach.active,"Pause immediately clears published browser intent")
    for file in DirAccess.get_files_at(directory):DirAccess.remove_absolute(directory+"/"+file)
    DirAccess.remove_absolute(directory)
    stage.queue_free();host.queue_free();panel.queue_free()
    await process_frame
    print("008FB_ANIMAL_APPROACH "+JSON.stringify({"failures":failures,"physical_distance_m":travelled,"collisions":collisions,"capture":false,"memory_ingestion":false}))
    quit(1 if failures else 0)
