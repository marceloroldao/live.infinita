extends SceneTree
var failures:=0
var checks:=0
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:failures+=1;push_error(label)
func ledge(x:float,_z:float)->float:return 0.0 if x<-99.7 else -1.0
func rise(x:float,_z:float)->float:return 0.0 if x<-99.7 else .5
func cliff(x:float,_z:float)->float:return 0.0 if x<-99.7 else -2.0
func flat(_x:float,_z:float)->float:return 0.0
func slope(x:float,_z:float)->float:return -0.4*(x+100.0)
func make_motion(host:Node3D,height:Callable):
    var m=load("res://world_map_local_motion.gd").new(height,512)
    m.gravity_enabled=true;m.inertial_enabled=true
    m._episodes.enabled=false;m._experience.working_memory.enabled=false
    var b=m.create_body(host,null);m.snap_body(b,Vector3(-100,0,0))
    return {"motion":m,"body":b}
func _initialize()->void:call_deferred("run")
func run()->void:
    var g=load("res://nov_ground_response.gd").new()
    var a:Dictionary=g.advance(0,-1,.1)
    check(a.height<0 and a.height>-.2 and not a.grounded,"One-metre drop falls incrementally")
    check(is_equal_approx(a.vertical_speed,-.981),"Gravity integrates 9.81 m/s2")
    var h:float=a.height
    for _i in range(30):h=g.advance(h,-1,.05).height
    check(is_equal_approx(h,-1.0) and not g.airborne and g.vertical_speed==0.0,"Fall lands without terrain penetration")
    g.reset();a=g.advance(0,-.05,.05)
    check(a.grounded and is_equal_approx(a.height,-.05),"Small descending slopes retain ground support")
    g.reset();a=g.advance(0,-1,0)
    check(a.height==0,"Zero-time step never teleports")
    g.reset();a=g.advance(0,-1,10)
    check(a.height>-.2,"Long frame bounds vertical displacement")
    for fps in [15,30,60]:
        g.reset();h=0.0
        for _i in range(fps):h=g.advance(h,-1,1.0/float(fps)).height
        check(is_equal_approx(h,-1.0) and not g.airborne,"Stable landing at "+str(fps)+" FPS")
    for fps in [15,30,60]:
        g.reset();h=0.0
        for _i in range(fps):
            var ground:=h-4.0/float(fps)
            h=g.advance(h,ground,1.0/float(fps),true).height
        check(not g.airborne and is_equal_approx(h,-4.0),"Continuous downhill support at "+str(fps)+" FPS")
    var host:=Node3D.new();root.add_child(host)
    var f:Dictionary=make_motion(host,Callable(self,"ledge"))
    await physics_frame;await physics_frame
    var current:=Vector3(-100,0,0)
    for _i in range(2):
        var r:Dictionary=f.motion.advance(current,Vector2.RIGHT,current,.1,f.body,host.get_world_3d().direct_space_state,false,8)
        current=r.position
    check(f.motion._ground_response.airborne and current.y<0 and current.y>-1,"Actual capsule starts a small physical fall")
    var start_x:=current.x
    for _i in range(20):
        if not f.motion._ground_response.airborne:break
        current=f.motion.advance(current,Vector2.RIGHT,current,.05,f.body,host.get_world_3d().direct_space_state,false,8).position
        check(is_equal_approx(current.x,start_x),"Airborne phase pauses horizontal movement")
    check(is_equal_approx(current.y,-1.0) and not f.motion._ground_response.airborne,"Actual body lands on authoritative terrain")
    check((f.body.position-Vector3(0,.9,0)).is_equal_approx(current),"Physical and published feet agree")
    f.motion.snap_body(f.body,Vector3(-100,0,0))
    check(not f.motion._ground_response.airborne and f.motion._ground_response.vertical_speed==0,"Explicit relocation clears falling state")
    f.body.queue_free();await physics_frame
    f=make_motion(host,Callable(self,"rise"));current=Vector3(-100,0,0)
    var last:Dictionary={}
    for _i in range(4):
        last=f.motion.advance(current,Vector2.RIGHT,current,.1,f.body,host.get_world_3d().direct_space_state,false,8);current=last.position
    check(current.x<-99.7 and last.reason=="step_too_high","Tall upward step is rejected")
    f.body.queue_free();await physics_frame
    f=make_motion(host,Callable(self,"cliff"));current=Vector3(-100,0,0)
    for _i in range(4):
        last=f.motion.advance(current,Vector2.RIGHT,current,.1,f.body,host.get_world_3d().direct_space_state,false,8);current=last.position
    check(current.x<-99.7 and not f.motion._ground_response.airborne,"Existing deep-drop gate remains authoritative")
    f.body.queue_free();await physics_frame
    f=make_motion(host,Callable(self,"flat"))
    var slab:=StaticBody3D.new();slab.collision_layer=1;host.add_child(slab);slab.position=Vector3(-100,.1,0)
    var c:=CollisionShape3D.new();c.shape=BoxShape3D.new();c.shape.size=Vector3(4,.2,4);slab.add_child(c)
    f.motion.snap_body(f.body,Vector3(-100,1,0));f.motion._ground_response.airborne=true
    await physics_frame;await physics_frame
    current=Vector3(-100,1,0)
    for _i in range(20):
        last=f.motion.advance_gravity(current,.05,f.body);current=last.position
        if last.collisions>0:break
    check(last.collisions>0 and current.y>=.19,"Vertical swept collision cannot cross solid support")
    host.queue_free();await process_frame
    for fps in [15,30,60]:
        var slope_host:=Node3D.new();root.add_child(slope_host)
        var slope_fixture:Dictionary=make_motion(slope_host,Callable(self,"slope"))
        await physics_frame
        var feet:=Vector3(-100,0,0)
        for _frame in range(fps):
            feet=slope_fixture.motion.advance(feet,Vector2.RIGHT,feet,1.0/float(fps),slope_fixture.body,slope_host.get_world_3d().direct_space_state,false,8).position
        check(not slope_fixture.motion._ground_response.airborne and is_equal_approx(feet.y,slope(feet.x,feet.z)),"Actual downhill capsule remains supported at "+str(fps)+" FPS")
        slope_host.queue_free();await physics_frame
    OS.set_environment("LIVE_INFINITA_NOV_GRAVITY","1")
    var stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    stage.get_node("LiveFeed").enabled=false
    await physics_frame
    check(stage._local_motion.gravity_enabled,"Native live scene activates configured gravity")
    var support:float=stage._height(stage._position.x,stage._position.z)
    stage._position.y=support+1.0
    stage._local_motion.snap_body(stage._walker,stage._position)
    stage._local_motion._ground_response.airborne=true
    var origin:Vector3=stage._position
    stage._advance_live_walk(.05)
    check(stage._position.y<origin.y and stage._position.y>support,"Live presentation executes gradual fall")
    for _i in range(30):
        if not stage._local_motion._ground_response.airborne:break
        stage._advance_live_walk(.05)
    check(is_equal_approx(stage._position.y,support) and is_equal_approx(stage._position.x,origin.x) and is_equal_approx(stage._position.z,origin.z),"Live scene lands before resuming horizontal intent")
    stage.queue_free();await process_frame
    OS.set_environment("LIVE_INFINITA_NOV_GRAVITY","0")
    OS.set_environment("LIVE_INFINITA_NOV_INERTIAL_MOTION","0")
    ProjectSettings.set_setting("live_infinita/nov_gravity",true)
    ProjectSettings.set_setting("live_infinita/nov_inertial_motion",true)
    stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    check(stage._local_motion.gravity_enabled and stage._local_motion.inertial_enabled,"Exported project settings activate both responses without native environment")
    stage.queue_free();await process_frame
    print("008FS_GRAVITY checks=",checks," failures=",failures)
    quit(1 if failures else 0)
