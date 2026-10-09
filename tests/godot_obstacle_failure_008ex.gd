extends "godot_physical_memory_comparison_008ed.gd"
var state_path: String
var geometry: String
var world_id: String
func box(holder: Node3D,center: Vector3,size: Vector3) -> void:
    var obstacle:=StaticBody3D.new()
    var shape:=CollisionShape3D.new()
    var volume:=BoxShape3D.new();volume.size=size;shape.shape=volume
    obstacle.add_child(shape);holder.add_child(obstacle);obstacle.position=center
func physical(holder: Node3D,label: String,enabled: bool,recall: Dictionary={}) -> Dictionary:
    var motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion._experience.storage=""
    motion._experience.trial_error_enabled=true
    motion._experience.memoria_enabled=false
    motion._experience.working_memory.storage="";motion._experience.working_memory.enabled=false
    motion._episodes.storage="";motion._episodes.enabled=true
    motion._episodes.set_context({"world_id":world_id,"observer_entity_id":"nov"})
    motion._pattern_collector.storage=state_path
    motion._pattern_collector.load_state()
    motion._pattern_collector.set_context(motion._episodes.context)
    motion._pattern_collector.set_enabled(enabled)
    if not recall.is_empty():
        check(motion._pattern_collector.local_rows.is_empty(),"Cold validation starts with empty local state")
        check(motion._pattern_collector.accept_recall(recall,Time.get_unix_time_from_system()),"Cold real recall accepted")
    motion.route_goal_id=label
    var body: CharacterBody3D=motion.create_body(holder,null)
    var current:=initial
    var ticks:=0
    var collisions:=0
    var contact: Dictionary={}
    var watchdog=load("res://nov_stuck_recovery.gd").new()
    var stopped:=false
    var started:=Time.get_ticks_msec()
    for i in range(2500):
        var value: Dictionary=motion.advance(current,Vector2.ZERO,destination,0.1,body,holder.get_world_3d().direct_space_state,true,4)
        current=value.get("position",current);ticks+=1;collisions+=int(value.get("collisions",0))
        if contact.is_empty() and motion._experience.contour.active:contact=motion._experience.contour.evidence()
        if value.get("reached",false):break
        if watchdog.observe(current,destination,0.1,true):stopped=true;break
    var arrived:=Vector2(current.x,current.z).distance_to(Vector2(destination.x,destination.z))<0.1
    # A real watchdog termination is failure; a test time limit is only censoring.
    var termination: String="arrived" if arrived else ("stuck_recovery" if stopped else "interrupted")
    if not arrived:motion.abort_journey("isolated physical watchdog" if stopped else "isolated budget exhausted",termination)
    var result: Dictionary={"arm":label,"arrived":arrived,"termination":termination,
        "distance_m":motion._journey.distance_m,"ticks":ticks,"simulated_seconds":ticks*0.1,
        "compute_wall_ms":Time.get_ticks_msec()-started,"collisions":collisions,"watchdog_stop":stopped,
        "watchdog_reason":watchdog.trigger_reason,"final_position":[current.x,current.z],
        "side":contact.get("initial_side",0),"recommendation":contact.get("pattern_recommendation",{}),
        "initial_evaluation":contact.get("pattern_evaluation",{}),
        "route_plan_builds":motion._experience.route_plan_builds,
        "status":motion._pattern_collector.status(),"facts":motion._pattern_collector.local_rows.duplicate(true)}
    check(collisions==0 and result.route_plan_builds==0,label+": actual guarded movement, no global planner")
    # Failure/abstention is an outcome, not a failed assertion. It must remain in the report.
    runs.append(result);body.queue_free();return result
func run() -> void:
    state_path=OS.get_environment("LIVE_INFINITA_NATIVE_PATTERN_STATE")
    geometry=OS.get_environment("LIVE_INFINITA_OBSTACLE_GEOMETRY")
    world_id="obstacle-failure-008ex-"+geometry
    if state_path.is_empty():quit(1);return
    if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
    initial=Vector3(-86,0,0);destination=Vector3(-68,0,0)
    var holder:=Node3D.new();root.add_child(holder)
    box(holder,Vector3(-80,2,0),Vector3(0.4,4,60))
    box(holder,Vector3(-90,2,30),Vector3(20,4,0.4))
    if geometry in ["pocket","closed"]:box(holder,Vector3(-90,2,-30),Vector3(20,4,0.4))
    if geometry=="closed":box(holder,Vector3(-100,2,0),Vector3(0.4,4,60))
    check(geometry in ["corner","pocket","closed"],"Known physical geometry")
    await physics_frame
    var recall_path:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")
    if recall_path.is_empty():
        for i in range(8):
            physical(holder,"perception_"+str(i),false)
            await physics_frame
            physical(holder,"memory_"+str(i),true)
            await physics_frame
        var file:=FileAccess.open(OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE"),FileAccess.WRITE)
        file.store_string(FileAccess.get_file_as_string(state_path));file.close()
    else:
        var recall: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(recall_path))
        physical(holder,"cold_perception",false)
        await physics_frame
        physical(holder,"cold_memory",true,recall)
        await physics_frame
    print("008EX_OBSTACLE_FAILURE "+JSON.stringify({"geometry":geometry,"world_id":world_id,
        "runs":runs,"failures":failures,"all_attempts_included":true}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
