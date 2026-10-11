extends SceneTree
var failures:=0
var checks:=0
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:failures+=1;push_error(label)
func flat(_x:float,_z:float)->float:return 0.0
func up(x:float,_z:float)->float:return .2*(x+100.0)
func down(x:float,_z:float)->float:return -.2*(x+100.0)
func flat_ground(x:float,z:float)->Vector3:return Vector3(x,0,z)
func up_ground(x:float,z:float)->Vector3:return Vector3(x,up(x,z),z)
func down_ground(x:float,z:float)->Vector3:return Vector3(x,down(x,z),z)
func bad_ground(x:float,z:float)->Vector3:return Vector3(x,NAN,z)
func mild_ground(x:float,z:float)->Vector3:return Vector3(x,.02*x,z)
func steep_ground(x:float,z:float)->Vector3:return Vector3(x,2*x,z)
func _initialize()->void:call_deferred("run")
func travel(height:Callable,fps:int,enabled:bool=true)->Dictionary:
    var host:=Node3D.new();root.add_child(host)
    var m=load("res://world_map_local_motion.gd").new(height,512)
    m.inertial_enabled=true;m.gravity_enabled=true;m.terrain_response_enabled=enabled
    m._episodes.enabled=false;m._experience.working_memory.enabled=false
    var body=m.create_body(host,null)
    var current:=Vector3(-100,0,0);m.snap_body(body,current)
    await physics_frame;await physics_frame
    var result:Dictionary={}
    for _i in range(fps*2):
        result=m.advance(current,Vector2.RIGHT,current,1.0/float(fps),body,host.get_world_3d().direct_space_state,false,8)
        current=result.position
    var out:Dictionary={"distance":current.x+100.0,"speed":body.velocity.x,"grounded":not m._ground_response.airborne,"policy":result,"status":m._journey.status()}
    host.queue_free();await physics_frame
    return out
func run()->void:
    var profile=load("res://nov_terrain_response.gd").new()
    var a:Dictionary=profile.sample(Vector3(-100,0,0),Vector2.RIGHT,Callable(self,"flat_ground"))
    var b:Dictionary=profile.sample(Vector3(-100,0,0),Vector2.RIGHT,Callable(self,"up_ground"))
    var c:Dictionary=profile.sample(Vector3(-100,0,0),Vector2.RIGHT,Callable(self,"down_ground"))
    check(a.speed_factor==1.0 and a.phase=="flat","Flat ground retains requested speed")
    check(is_equal_approx(b.grade,.2) and b.phase=="uphill" and b.speed_factor<1,"Observed uphill geometry reduces speed")
    check(c.phase=="downhill" and c.speed_factor>b.speed_factor and c.speed_factor<1,"Descent has bounded control speed")
    check(not profile.sample(Vector3.ZERO,Vector2.RIGHT,Callable(self,"bad_ground")).sample_valid,"Invalid geometry cannot produce usable speed")
    check(profile.sample(Vector3.ZERO,Vector2.ZERO,Callable(self,"flat_ground")).speed_factor==1.0,"Idle direction has no invented slope")
    check(profile.sample(Vector3(-100,0,0),Vector2.LEFT,Callable(self,"up_ground")).phase=="downhill","Grade follows travel direction rather than map axis")
    check(profile.sample(Vector3.ZERO,Vector2.RIGHT,Callable(self,"mild_ground")).speed_factor==1.0,"Small slopes stay in the dead zone")
    var steep:Dictionary=profile.sample(Vector3.ZERO,Vector2.RIGHT,Callable(self,"steep_ground"))
    check(is_equal_approx(steep.grade,.7) and steep.speed_factor>0.0,"Speed response remains bounded on steep samples; traversal still decides passage")
    for fps in [15,30,60]:
        var level:Dictionary=await travel(Callable(self,"flat"),fps)
        var climb:Dictionary=await travel(Callable(self,"up"),fps)
        var descent:Dictionary=await travel(Callable(self,"down"),fps)
        check(climb.distance<level.distance*.9 and descent.distance>climb.distance and descent.distance<level.distance,"Native distance reflects slope at "+str(fps)+" FPS")
        check(absf(level.speed-8.0)<.002 and absf(climb.speed-8.0/1.4)<.02 and absf(descent.speed-8.0/1.15)<.02,"Native steady speeds match local response at "+str(fps)+" FPS")
        check(climb.grounded and descent.grounded,"Slope response retains physical support at "+str(fps)+" FPS")
        check(climb.status.terrain_motion.phase=="uphill" and absf(climb.policy.terrain_motion.actual_speed_mps-climb.speed)<.02,"Diagnostic reports actual executed speed")
        print("008FU_SLOPE fps=",fps," flat=",level.distance," uphill=",climb.distance," downhill=",descent.distance," speeds=",[level.speed,climb.speed,descent.speed])
    var legacy:Dictionary=await travel(Callable(self,"up"),30,false)
    check(absf(legacy.speed-8.0)<.02,"Disabled response preserves prior uphill speed")
    OS.set_environment("LIVE_INFINITA_NOV_TERRAIN_RESPONSE","0")
    ProjectSettings.set_setting("live_infinita/nov_terrain_response",true)
    var stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    check(stage._local_motion.terrain_response_enabled,"Exported setting enables terrain response in the scene")
    stage.queue_free();await process_frame
    print("008FU_TERRAIN checks=",checks," failures=",failures)
    quit(1 if failures else 0)
