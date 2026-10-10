extends SceneTree
var failures:=0
const WORLD:="approach-context-008ff"
func allowed(point:Vector3)->Dictionary:return {"allowed":true,"position":point}
func _initialize()->void:call_deferred("run")
func body_at(host:Node3D,point:Vector3,size:Vector3)->StaticBody3D:
    var b:=StaticBody3D.new();b.collision_layer=1;host.add_child(b);b.position=point
    var c:=CollisionShape3D.new();c.shape=BoxShape3D.new();c.shape.size=size;b.add_child(c);return b
func run()->void:
    var host:=Node3D.new();root.add_child(host)
    var nov:=CharacterBody3D.new();nov.collision_layer=1;nov.collision_mask=1;host.add_child(nov);nov.position=Vector3(0,.9,0)
    var shape:=CollisionShape3D.new();shape.shape=CapsuleShape3D.new();shape.shape.radius=.44;shape.shape.height=1.8;nov.add_child(shape)
    var sensor=load("res://nov_visual_perception.gd").new()
    var a:=body_at(host,Vector3(16,.2,0),Vector3(.5,.4,.5))
    var b:=body_at(host,Vector3(10,.2,20),Vector3(.5,.4,.5))
    sensor.register_target(a,WORLD+":rabbit:0","rabbit",WORLD,Vector3.ZERO)
    sensor.register_target(b,WORLD+":rabbit:1","rabbit",WORLD,Vector3.ZERO)
    var reverse:=OS.get_environment("LIVE_INFINITA_APPROACH_TEST_REVERSE")=="1"
    # Low fence blocks the capsule while both eye rays remain unobstructed.
    var hidden:=OS.get_environment("LIVE_INFINITA_APPROACH_TEST_HIDDEN")=="1"
    if reverse:
        body_at(host,Vector3(2.68,.2,5.36) if hidden else Vector3(1.5,.2,3),Vector3(2,.4,.4))
    else:
        body_at(host,Vector3(6,.2,0) if hidden else Vector3(3.5,.2,0),Vector3(.4,.4,4))
    await physics_frame;await physics_frame
    var start:=int(OS.get_environment("LIVE_INFINITA_APPROACH_TEST_CLOCK"))
    var observation:Dictionary=sensor.scan(nov,Vector3(1,0,1).normalized(),host.get_world_3d().direct_space_state,WORLD,start,1.0)
    var candidates:Array=[]
    for row in observation.visible_entities:
        var p:=Vector3(row.observed_position_m[0],row.observed_position_m[1],row.observed_position_m[2])
        var direction:=Vector3(p.x-nov.position.x,0,p.z-nov.position.z).normalized()
        var blocked:=nov.test_move(nov.global_transform,direction*4.0)
        candidates.append({"entity_id":row.entity_id,"distance_m":Vector2(nov.position.x,nov.position.z).distance_to(Vector2(p.x,p.z)),
            "context":{"profile":"capsule044-height18-sweep4-v1","sweep_m":4.0,"blocked_ahead":blocked,"sample_logical_ms":start}})
    if candidates.size()!=2:push_error("Both candidate rabbits must be physically visible");quit(1);return
    var selected:=OS.get_environment("LIVE_INFINITA_APPROACH_TEST_TARGET")
    if selected.is_empty():
        print("008FF_PHYSICAL "+JSON.stringify({"candidates":candidates,"probe":true}));quit(0);return
    var approach=load("res://nov_animal_approach.gd").new();approach.enabled=true
    approach.choose(nov.position,WORLD,start,Callable(self,"allowed"))
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
    for i in range(220):
        now=start+i*100
        if i>0:sensor.scan(nov,Vector3(1,0,1).normalized(),host.get_world_3d().direct_space_state,WORLD,now,1.0)
        var choice:Dictionary=approach.choose(nov.position,WORLD,now,Callable(self,"allowed"))
        if choice.is_empty():break
        var point:=Vector3(choice.goal[0],nov.position.y,choice.goal[2])
        var before:=nov.position
        if nov.move_and_collide((point-before).normalized()*.1)!=null:collisions+=1
        travelled+=nov.position.distance_to(before)
        await physics_frame
    if approach._results.size()!=1:push_error("Physical attempt must terminate once");quit(1);return
    var fact:Dictionary=approach._results[0]
    if absf(fact.distance_m-travelled)>.0001:push_error("Measured controller distance must match body distance");quit(1);return
    var initial_context:Dictionary={}
    for candidate in candidates:
        if candidate.entity_id==fact.entity_id:initial_context=candidate.context
    print("008FF_PHYSICAL "+JSON.stringify({"candidates":candidates,"probe":false,
        "context_fact":{"approach":fact,"context":initial_context,"contacts":collisions},"fact":fact,"distance_m":travelled,"contacts":collisions,"reverse":reverse,
        "motion_model":"incremental direct CharacterBody approach; full scene contour navigation not exercised","world_write_authority":false}))
    quit(0)
