extends SceneTree
var failures:=0
var checks:=0
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:failures+=1;push_error(label)
func flat(_x:float,_z:float)->float:return 0.0
func _initialize()->void:call_deferred("run")
func run()->void:
    for fps in [15,30,60]:
        for target in [Vector2(0,1),Vector2(-1,0),Vector2(0,-1)]:
            var script:=OS.get_environment("LIVE_INFINITA_TURN_TEST_RESPONSE")
            var response=load("res://nov_locomotion_response.gd" if script.is_empty() else script).new()
            response.velocity=Vector2(8,0)
            var position:=Vector2.ZERO
            var last_yaw:=0.0
            var turn:=0.0
            var dt:=1.0/float(fps)
            var reached:=false
            for _i in range(fps*5):
                if position.distance_to(target)<.03:reached=true;break
                # Production supplies a speed*dt candidate towards the local waypoint.
                var candidate:=position.move_toward(target,8.0*dt)
                var move:Vector2=response.displacement(position,candidate,target.normalized()*100.0,8,dt)
                if move.length()>.002:
                    var yaw:=atan2(move.y,move.x)
                    turn+=absf(angle_difference(last_yaw,yaw));last_yaw=yaw
                position+=move
                response.executed(move,dt,false)
            check(reached,"Short waypoint reached at "+str(fps)+" FPS")
            check(turn<TAU,"Sharp turn does not produce a full orbit at "+str(fps)+" FPS")
            print("008FT_TURN fps=",fps," target=",target," rotation_deg=",rad_to_deg(turn)," remaining_m=",position.distance_to(target))
    var host:=Node3D.new();root.add_child(host)
    var motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion.inertial_enabled=true;motion.gravity_enabled=true
    motion._episodes.enabled=false;motion._experience.working_memory.enabled=false
    var body=motion.create_body(host,null)
    var current:=Vector3(-100,0,0);motion.snap_body(body,current)
    motion._locomotion.velocity=Vector2(8,0)
    await physics_frame;await physics_frame
    var goal:=Vector2(-100,1)
    var angle:=0.0;var rotation_sum:=0.0
    for _i in range(100):
        var from:=Vector2(current.x,current.z)
        if from.distance_to(goal)<.03:break
        var input:Vector2=(goal-from).limit_length(8.0/15.0)/(8.0/15.0)
        var result:Dictionary=motion.advance(current,input,current,1.0/15.0,body,host.get_world_3d().direct_space_state,false,8)
        current=result.position
        var move:=Vector2(current.x,current.z)-from
        if move.length()>.002:
            var yaw:=atan2(move.y,move.x)
            rotation_sum+=absf(angle_difference(angle,yaw));angle=yaw
    check(Vector2(current.x,current.z).distance_to(goal)<.03,"Actual native capsule reaches short corner with gravity and inertia active")
    check(rotation_sum<TAU,"Actual native movement avoids a full spin")
    host.queue_free();await process_frame
    print("008FT_TURN_BRAKING checks=",checks," failures=",failures)
    quit(1 if failures else 0)
