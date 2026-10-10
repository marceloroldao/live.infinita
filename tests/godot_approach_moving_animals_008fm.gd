extends SceneTree
var failures:=0
func flat(_x:float,_z:float)->float:return 0.0
func verify_context_checkpoint(_approach:RefCounted)->void:pass
const WORLD:="approach-moving-animals-008fm"
func allowed(point:Vector3)->Dictionary:return {"allowed":true,"position":point}
func _initialize()->void:call_deferred("run")
func body_at(host:Node3D,point:Vector3,size:Vector3)->StaticBody3D:
    var b:=StaticBody3D.new();b.collision_layer=1;host.add_child(b);b.position=point
    var c:=CollisionShape3D.new();c.shape=BoxShape3D.new();c.shape.size=size;b.add_child(c);return b
func animal_at(host:Node3D,point:Vector3)->CharacterBody3D:
    var b:=CharacterBody3D.new();b.collision_layer=1;b.collision_mask=1
    host.add_child(b);b.position=point
    var c:=CollisionShape3D.new();c.shape=BoxShape3D.new();c.shape.size=Vector3(.5,.4,.5);b.add_child(c)
    return b
func setting(name:String,fallback:float,low:float,high:float)->float:
    var text:=OS.get_environment(name)
    var value:=fallback if text.is_empty() else float(text)
    if not is_finite(value) or value<low or value>high:
        push_error("Invalid isolated fixture setting");quit(1);return fallback
    return value
func run()->void:
    var animal_speed:=setting("LIVE_INFINITA_TEST_ANIMAL_SPEED",0.5,0.0,2.0)
    var animal_steps:=0
    var speed:=setting("LIVE_INFINITA_TRANSFER_SPEED",4.0,2.0,6.0)
    var near_m:=setting("LIVE_INFINITA_TRANSFER_NEAR",16.0,13.0,17.9)
    var far_m:=setting("LIVE_INFINITA_TRANSFER_FAR",22.0,20.0,23.0)
    var wall_m:=setting("LIVE_INFINITA_TRANSFER_WALL_AT",6.0,5.0,14.0)
    var wall_length:=setting("LIVE_INFINITA_TRANSFER_WALL_LENGTH",80.0,60.0,100.0)
    var serial:=int(setting("LIVE_INFINITA_TRANSFER_ANIMAL_SERIAL",0.0,0.0,100.0))
    var host:=Node3D.new();root.add_child(host)
    var motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion._experience.storage="";motion._experience.memoria_enabled=false;motion._experience.trial_error_enabled=true
    motion._experience.working_memory.storage="";motion._experience.working_memory.enabled=false
    motion._episodes.storage="";motion._episodes.enabled=false
    motion._pattern_collector.storage="";motion._pattern_collector.set_enabled(false)
    var nov:CharacterBody3D=motion.create_body(host,null)
    var current:=Vector3.ZERO;motion.snap_body(nov,current)
    # Call the production heading/orientation methods without starting the full world.
    var rig=load("res://world_map_preview.gd").new()
    rig._walker=nov
    rig._camera_forward=Vector3(1,0,1).normalized()
    rig._orient_nov_visual()
    var sensor=load("res://nov_visual_perception.gd").new()
    var a:=animal_at(host,Vector3(near_m,.2,0))
    var b:=animal_at(host,Vector3(1,.2,far_m))
    sensor.register_target(a,WORLD+":rabbit:"+str(serial),"rabbit",WORLD,Vector3.ZERO)
    sensor.register_target(b,WORLD+":rabbit:"+str(serial+1),"rabbit",WORLD,Vector3.ZERO)
    var reverse:=OS.get_environment("LIVE_INFINITA_APPROACH_TEST_REVERSE")=="1"
    # A low, long fence requires a detour beyond this bounded attempt.
    # Both animals remain ray-visible; the barrier starts outside the four-metre sweep.
    if reverse:
        body_at(host,Vector3(0,.2,wall_m),Vector3(wall_length,.4,.4))
    else:
        body_at(host,Vector3(wall_m,.2,0),Vector3(.4,.4,wall_length))
    await physics_frame;await physics_frame
    var start:=int(OS.get_environment("LIVE_INFINITA_APPROACH_TEST_CLOCK"))
    var observation:Dictionary=sensor.scan(nov,nov.global_basis.z,host.get_world_3d().direct_space_state,WORLD,start,1.0)
    var candidates:Array=[]
    for row in observation.visible_entities:
        var p:=Vector3(row.observed_position_m[0],row.observed_position_m[1],row.observed_position_m[2])
        var direction:=Vector3(p.x-nov.position.x,0,p.z-nov.position.z).normalized()
        var blocked:=nov.test_move(nov.global_transform,direction*4.0)
        candidates.append({"entity_id":row.entity_id,"distance_m":Vector2(nov.position.x,nov.position.z).distance_to(Vector2(p.x,p.z)),
            "context":{"profile":"capsule044-height18-sweep4-native-contour-v1","sweep_m":4.0,"blocked_ahead":blocked,"sample_logical_ms":start}})
    if candidates.size()!=2:push_error("Both candidate rabbits must be physically visible");quit(1);return
    var selected:=OS.get_environment("LIVE_INFINITA_APPROACH_TEST_TARGET")
    if selected.is_empty():
        print("008FM_PHYSICAL "+JSON.stringify({"candidates":candidates,"probe":true,"fixture":{"speed_m_s":speed,"near_m":near_m,"far_m":far_m,"wall_at_m":wall_m,"wall_length_m":wall_length,"animal_serial":serial,"animal_speed_m_s":animal_speed}}));rig.free();quit(0);return
    var approach=load("res://nov_animal_approach.gd").new();approach.enabled=true
    approach.context_enabled=true;approach.context_probe=Callable(motion,"approach_context")
    approach.configure(OS.get_environment("LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE"))
    approach.choose(current,WORLD,start,Callable(self,"allowed"))
    sensor.observation_ready.connect(Callable(approach,"observe"))
    approach.observe(observation)
    # Target is supplied by the experimental selector from the same two fresh sightings.
    if selected!="perception":
        if not approach._seen.has(selected):push_error("Chosen target lacks physical sight");quit(1);return
        for id in approach._seen.keys():
            if id!=selected:approach._seen.erase(id)
    var collisions:=0
    var travelled:=0.0
    var now:=start
    var elapsed:=0.0
    var scans:=1
    for i in range(220):
        now=start+i*100
        if i>0:
            elapsed+=.1
            if elapsed>=.25:
                elapsed=0.0
                scans+=1
                sensor.scan(nov,nov.global_basis.z,host.get_world_3d().direct_space_state,WORLD,now,1.0)
        var choice:Dictionary=approach.choose(current,WORLD,now,Callable(self,"allowed"))
        if choice.is_empty():break
        var point:=Vector3(choice.goal[0],current.y,choice.goal[2])
        var before:=current
        var movement:Dictionary=motion.advance(current,Vector2.ZERO,point,.1,nov,host.get_world_3d().direct_space_state,true,speed)
        approach.observe_movement(movement)
        current=movement.get("position",current);collisions+=int(movement.get("collisions",0))
        rig._update_camera_heading(before,current,.1)
        rig._orient_nov_visual()
        travelled+=current.distance_to(before)
        # Environment advances after Nov's decision: neither selector nor controller
        # receives this velocity or a future target position. Collision is physical.
        a.move_and_collide(Vector3(animal_speed*.1,0,0))
        b.move_and_collide(Vector3(0,0,animal_speed*.1))
        animal_steps+=1
        await physics_frame
    if approach._results.size()!=1:push_error("Physical attempt must terminate once");quit(1);return
    var fact:Dictionary=approach._results[0]
    if absf(fact.distance_m-travelled)>.0001:push_error("Measured controller distance must match body distance");quit(1);return
    if approach._context_history.records.size()!=1:push_error("Native collector must preserve one measured contextual outcome");quit(1);return
    var initial_context:Dictionary={}
    for candidate in candidates:
        if candidate.entity_id==fact.entity_id:initial_context=candidate.context
    if approach._context_history.records[0].context!=initial_context:push_error("Native collector context must match physical probe");quit(1);return
    if approach._context_history.records[0].contacts!=collisions:push_error("Stored contacts must match actual native movement");quit(1);return
    verify_context_checkpoint(approach)
    print("008FM_PHYSICAL "+JSON.stringify({"candidates":candidates,"probe":false,"fixture":{"speed_m_s":speed,"near_m":near_m,"far_m":far_m,"wall_at_m":wall_m,"wall_length_m":wall_length,"animal_serial":serial,"animal_speed_m_s":animal_speed},
        "context_fact":{"approach":fact,"context":initial_context,"contacts":collisions},"fact":fact,"distance_m":travelled,"contacts":collisions,"reverse":reverse,
        "motion_model":"native local motion; production stabilized body heading and 0.25s scan scheduler; moving collidable animals; flat terrain", "scan_count":scans,"animal_steps":animal_steps,"animal_positions_final":{"near":[a.position.x,a.position.y,a.position.z],"far":[b.position.x,b.position.y,b.position.z]},"future_position_given_to_controller":false,
        "route_plan_builds":motion._experience.route_plan_builds,"navigation_status":motion._experience.last_decision_source,"world_write_authority":false}))
    rig.free()
    quit(1 if failures else 0)
