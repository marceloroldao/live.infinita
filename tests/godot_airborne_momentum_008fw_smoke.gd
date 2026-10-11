extends SceneTree
var checks:=0
var failures:=0
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:failures+=1;push_error(label)
func _initialize()->void:call_deferred("run")
func flat(_x:float,_z:float)->float:return 0.0
func ledge(x:float,_z:float)->float:return 0.0 if x<-99.7 else -1.0
func cliff(x:float,_z:float)->float:return 0.0 if x<-99.7 else (-1.0 if x<-99.0 else -3.0)
func invalid_ground(x:float,z:float)->float:return NAN if x>=-99.0 else ledge(x,z)
func boundary_ledge(x:float,_z:float)->float:return 0.0 if x<99.3 else -1.0
func river_ledge(x:float,_z:float)->float:return 0.0 if x<21.7 else -1.0
func lake(x:float,_z:float)->Dictionary:
    return {"walkable":false,"surface":"water","reason":"cognitive_lake","escape_depth_m":1.0} if x>=-99.0 else {"walkable":true}
func make_fixture(height:Callable,enabled:bool=true,start:Vector3=Vector3(-100,0,0),half_m:float=512.0,surface:Callable=Callable())->Dictionary:
    var host:=Node3D.new();root.add_child(host)
    var m=load("res://world_map_local_motion.gd").new(height,half_m,surface)
    m.inertial_enabled=true;m.gravity_enabled=true;m.airborne_momentum_enabled=enabled;m.terrain_response_enabled=true
    m._episodes.enabled=false;m._experience.working_memory.enabled=false
    var body=m.create_body(host,null);m.snap_body(body,start)
    return {"host":host,"m":m,"body":body,"position":start}
func depart(f:Dictionary,dt:float)->bool:
    for _i in range(30):
        var r:Dictionary=f.m.advance(f.position,Vector2.RIGHT,f.position,dt,f.body,f.host.get_world_3d().direct_space_state,false,8)
        f.position=r.position
        if f.m._ground_response.airborne:return true
    return false
func run()->void:
    for fps in [15,30,60]:
        var f:Dictionary=make_fixture(Callable(self,"ledge"));await physics_frame;await physics_frame
        var dt:=1.0/float(fps)
        check(depart(f,dt),"Capsule departs ledge at "+str(fps)+" FPS")
        var carried:float=f.m._air_velocity.x
        var origin:Vector3=f.position
        check(carried>0.0 and absf(f.body.velocity.x-carried)<.001,"Departure captures executed physical velocity")
        var last:Dictionary={}
        var constant:=true
        var frame_count:=0
        for _i in range(fps):
            var before:Vector3=f.position
            # Opposing input and goal must not steer the airborne body.
            last=f.m.advance(before,Vector2.LEFT,before-Vector3(100,0,0),dt,f.body,f.host.get_world_3d().direct_space_state,false,8)
            f.position=last.position;frame_count+=1
            constant=constant and absf((f.position.x-before.x)/dt-carried)<.003
            if last.grounded:break
        check(constant and f.position.x>origin.x+.5,"Airborne carry has no steering or manufactured acceleration")
        check(last.grounded and is_equal_approx(f.position.y,-1.0),"Airborne carry lands on canonical terrain")
        check(absf(f.m._locomotion.velocity.x-carried)<.001 and f.m._air_velocity==Vector2.ZERO,"Landing transfers surviving velocity back to supported inertia")
        check(absf(last.terrain_motion.actual_speed_mps-carried)<.003 and last.airborne_momentum,"Diagnostics report actual carried horizontal motion")
        check((f.body.position-Vector3(0,.9,0)).is_equal_approx(f.position),"Published feet remain the physical capsule feet")
        last=f.m.advance(f.position,Vector2.LEFT,f.position,dt,f.body,f.host.get_world_3d().direct_space_state,false,8)
        check(f.body.velocity.x>=0.0 and f.body.velocity.x<carried,"Supported reversal brakes the surviving momentum")
        check(f.m._journey.completed_steps==0 and f.m._journey.causal_memoria_steps==0,"Physical flight fabricates no learned decision or success")
        print("008FW_FLIGHT fps=",fps," speed=",carried," air_distance=",f.position.x-origin.x," frames=",frame_count)
        f.host.queue_free();await physics_frame
    var legacy:Dictionary=make_fixture(Callable(self,"ledge"),false);await physics_frame
    check(depart(legacy,.1),"Disabled fixture still falls")
    var old_x:float=legacy.position.x
    legacy.position=legacy.m.advance_gravity(legacy.position,.05,legacy.body).position
    check(is_equal_approx(legacy.position.x,old_x),"Disabled response preserves paused horizontal gravity")
    legacy.host.queue_free();await physics_frame
    # Physical sweep and the traversal gate stop momentum at a solid wall.
    var f:Dictionary=make_fixture(Callable(self,"ledge"))
    var wall:=StaticBody3D.new();wall.collision_layer=1;f.host.add_child(wall);wall.position=Vector3(-98.5,1,0)
    var shape:=CollisionShape3D.new();shape.shape=BoxShape3D.new();shape.shape.size=Vector3(.2,5,4);wall.add_child(shape)
    await physics_frame;await physics_frame
    check(depart(f,.1),"Wall fixture starts a permitted fall")
    var last:Dictionary={}
    var blocked:=false
    for _i in range(20):
        last=f.m.advance_gravity(f.position,.05,f.body);f.position=last.position
        blocked=blocked or last.horizontal_blocked
        if last.grounded:break
    check(blocked and f.position.x<=-99.04 and f.m._locomotion.velocity==Vector2.ZERO,"Airborne capsule cannot cross a solid wall")
    check(last.grounded and is_equal_approx(f.position.y,-1.0),"Blocked horizontal drift still permits vertical landing")
    f.host.queue_free();await physics_frame
    for kind in ["deep_drop","lake","boundary","river","invalid_geometry"]:
        var height:Callable=Callable(self,"invalid_ground") if kind=="invalid_geometry" else Callable(self,"cliff") if kind=="deep_drop" else (Callable(self,"boundary_ledge") if kind=="boundary" else (Callable(self,"river_ledge") if kind=="river" else Callable(self,"ledge")))
        var start:=Vector3(99,0,0) if kind=="boundary" else (Vector3(21.4,0,0) if kind=="river" else Vector3(-100,0,0))
        f=make_fixture(height,true,start,101 if kind=="boundary" else 512,Callable(self,"lake") if kind=="lake" else Callable())
        await physics_frame
        check(depart(f,.1),kind+" fixture starts a permitted fall")
        var reason:=""
        for _i in range(20):
            last=f.m.advance_gravity(f.position,.05,f.body);f.position=last.position
            if last.horizontal_blocked:reason=last.reason
            if last.grounded:break
        var expected:="terrain_sample_unavailable" if kind=="invalid_geometry" else "step_too_high" if kind=="deep_drop" else ("cognitive_lake" if kind=="lake" else ("map_boundary" if kind=="boundary" else "river_without_bridge"))
        check(reason==expected and last.grounded and f.m._locomotion.velocity==Vector2.ZERO,"Airborne drift preserves "+kind+" gate and vertical landing")
        f.host.queue_free();await physics_frame
    f=make_fixture(Callable(self,"ledge"));await physics_frame;check(depart(f,.1),"Relocation fixture carries momentum")
    f.m.snap_body(f.body,Vector3(-100,0,0))
    check(f.m._air_velocity==Vector2.ZERO and not f.m._ground_response.airborne,"Relocation clears carried flight state")
    f.m._ground_response.airborne=true;f.m._air_velocity=Vector2(3,0);f.position=Vector3(-101,.5,0)
    var same:Dictionary=f.m.advance_gravity(f.position,0,f.body)
    check(same.position.is_equal_approx(f.position),"Zero elapsed time cannot move airborne capsule")
    same=f.m.advance_gravity(f.position,10,f.body)
    check(absf(same.position.x-f.position.x-.3)<.001 and same.position.y<f.position.y,"Long frame bounds both horizontal and vertical flight integration")
    f.host.queue_free();await physics_frame
    OS.set_environment("LIVE_INFINITA_NOV_AIRBORNE_MOMENTUM","0")
    ProjectSettings.set_setting("live_infinita/nov_airborne_momentum",true)
    var stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    check(stage._local_motion.airborne_momentum_enabled,"Exported scene activates carried momentum")
    stage._local_motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),stage._layout.half_m)
    stage._local_motion.gravity_enabled=true;stage._local_motion.inertial_enabled=true;stage._local_motion.airborne_momentum_enabled=true
    stage._position=Vector3(-128.05,.6,-32)
    stage._local_motion.snap_body(stage._walker,stage._position)
    stage._local_motion._ground_response.airborne=true;stage._local_motion._air_velocity=Vector2(4,0)
    var before:Vector3=stage._position
    var previous_cell:int=stage._cell(before.x)
    stage._advance_live_walk(.05)
    var next_cell:int=stage._cell(stage._position.x)
    check(next_cell==previous_cell+1 and stage._position.y<before.y,"Live scene carries horizontal motion during the physical fall")
    var tile_id:="%d:%d" % [next_cell+stage._layout.active_radius_tiles,stage._cell(stage._position.z)]
    check(stage._tiles.has(tile_id),"Airborne tile crossing updates the active terrain footprint")
    check(stage._walker.get_node("NovVisual").desired_action=="fall","Carried horizontal motion retains the physical fall posture")
    stage.queue_free();await process_frame
    print("008FW_AIRBORNE_MOMENTUM checks=",checks," failures=",failures)
    quit(1 if failures else 0)
