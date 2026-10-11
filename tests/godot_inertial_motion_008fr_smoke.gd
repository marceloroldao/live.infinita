extends SceneTree
var failures := 0
var checks := 0
func check(ok: bool, label: String) -> void:
    checks+=1
    if not ok: failures+=1; push_error(label)
func flat(_x:float,_z:float)->float:return 0.0
func _initialize()->void:call_deferred("run")
func run()->void:
    var r=load("res://nov_locomotion_response.gd").new()
    var p:=Vector2.ZERO
    var d:Vector2=r.displacement(p,Vector2(100,0),Vector2(100,0),8,.05)
    check(is_equal_approx(d.length(),.045),"Acceleration starts at 18 m/s2")
    p+=d
    var previous:Vector2=r.velocity
    r.displacement(p,Vector2(0,100),Vector2(0,100),8,.05)
    check(r.velocity.distance_to(previous)<=1.2+0.001 and r.velocity.x>0,"Corner retains momentum with bounded acceleration")
    r.velocity=Vector2(8,0)
    r.displacement(p,Vector2(-100,0),Vector2(-100,0),8,.05)
    check(r.velocity.x>0 and is_equal_approx(r.velocity.x,6.8),"Reversal brakes before direction changes")
    r.executed(Vector2.ZERO,.05,true)
    check(r.velocity==Vector2.ZERO,"Collision cancels residual momentum")
    p=Vector2.ZERO
    for i in range(200):
        d=r.displacement(p,Vector2(2,0),Vector2(2,0),8,.05);p+=d
    check(p.distance_to(Vector2(2,0))<.04 and p.x<=2.0001,"Braking arrives without overshoot")
    r.stop();r.displacement(p,Vector2(100,0),Vector2(100,0),8,10)
    check(r.velocity.length()<=1.8+.001,"Long frame bounds acceleration")
    for fps in [15,30,60]:
        r.stop();p=Vector2.ZERO
        var dt:=1.0/float(fps)
        for _frame in range(fps):
            p+=r.displacement(p,Vector2(100,0),Vector2(100,0),8,dt)
        check(is_equal_approx(r.velocity.length(),8.0) and p.x>6.0 and p.x<6.7,"Stable bounded response at "+str(fps)+" FPS")
    var host:=Node3D.new();root.add_child(host)
    var motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion.inertial_enabled=true
    motion._episodes.enabled=false;motion._experience.working_memory.enabled=false
    var body=motion.create_body(host,null)
    var current:=Vector3(-100,0,0);motion.snap_body(body,current)
    var obstacle:=StaticBody3D.new();obstacle.collision_layer=1;host.add_child(obstacle);obstacle.position=Vector3(-97,1,0)
    var shape:=CollisionShape3D.new();shape.shape=BoxShape3D.new();shape.shape.size=Vector3(.4,3,10);obstacle.add_child(shape)
    await physics_frame;await physics_frame
    var initial:Dictionary=motion.advance(current,Vector2.RIGHT,current,.05,body,host.get_world_3d().direct_space_state,false,8)
    current=initial.position
    check(current.x>-100 and current.x<-99.9,"Actual collider displacement accelerates gradually")
    for i in range(100):
        var result:Dictionary=motion.advance(current,Vector2.RIGHT,current,.05,body,host.get_world_3d().direct_space_state,false,8)
        current=result.position
    check(current.x<-97.6 and current.x>-100,"Actual capsule cannot cross wall under momentum")
    check(motion._locomotion.velocity==Vector2.ZERO,"Blocked physical movement resets velocity")
    host.queue_free();await process_frame
    print("008FR_INERTIAL checks=",checks," failures=",failures)
    quit(1 if failures else 0)
