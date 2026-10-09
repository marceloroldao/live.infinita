extends "godot_native_patterns_008eh.gd"
# Same native travel scaffold; recall merges with fresh local outcomes.
func native_travel(holder: Node3D,label: String, enabled_patterns: bool=true, recall: Dictionary={},minimum_outcomes: int=1) -> Dictionary:
    var motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion._experience.storage=""
    motion._experience.trial_error_enabled=true
    motion._experience.working_memory.storage=""
    motion._experience.working_memory.enabled=false
    motion._episodes.storage=""
    motion._episodes.enabled=true
    motion._episodes.set_context({"world_id":"native-pattern-008eh","observer_entity_id":"nov"})
    motion._pattern_collector.storage=state_path
    motion._pattern_collector.load_state()
    motion._pattern_collector.set_context(motion._episodes.context)
    motion._pattern_collector.set_enabled(enabled_patterns)
    if not recall.is_empty():
        check(motion._pattern_collector.accept_recall(recall,Time.get_unix_time_from_system()),"Verified native recall accepted")
    motion.route_goal_id=label
    var body: CharacterBody3D=motion.create_body(holder,null)
    var current:=initial
    var collisions:=0
    var ticks:=0
    var contact: Dictionary={}
    var watchdog=load("res://nov_stuck_recovery.gd").new()
    var rescued:=false
    for i in range(2500):
        var value: Dictionary=motion.advance(current,Vector2.ZERO,destination,0.1,body,holder.get_world_3d().direct_space_state,true,4)
        current=value.get("position",current);ticks+=1
        collisions+=int(value.get("collisions",0))
        if contact.is_empty() and motion._experience.contour.active:contact=motion._experience.contour.evidence()
        if watchdog.observe(current,destination,0.1,true):rescued=true;break
        if value.get("reached",false):break
    var arrived:=current.distance_to(destination)<0.1
    var result: Dictionary={"arm":label,"arrived":arrived,"distance_m":motion._journey.distance_m,
        "ticks":ticks,"simulated_seconds":ticks*0.1,"collisions":collisions,"rescued":rescued,
        "side":contact.get("initial_side",0),"recommendation":contact.get("pattern_recommendation",{}),
        "status":motion._pattern_collector.status(),"route_plan_builds":motion._experience.route_plan_builds}
    check(arrived and collisions==0 and not rescued and result.route_plan_builds==0,label+": physically valid native journey")
    if enabled_patterns:
        check(motion._pattern_collector.observed>=minimum_outcomes,label+": actual native collector records independent local outcomes")
    runs.append(result)
    body.queue_free()
    return result
func run() -> void:
    state_path=OS.get_environment("LIVE_INFINITA_NATIVE_PATTERN_STATE")
    check(not state_path.is_empty(),"Isolated state required")
    if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
    var holder:=Node3D.new();root.add_child(holder)
    var phase:=OS.get_environment("LIVE_INFINITA_SEQUENCE_PHASE")
    if phase=="training":
        opening_z=-130
        await reset_wall(holder)
        for i in range(4):
            native_travel(holder,"training_perception_"+str(i),false)
            await physics_frame
        for i in range(4):
            native_travel(holder,"training_memory_"+str(i))
            await physics_frame
    else:
        initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60)
        opening_z=float(OS.get_environment("LIVE_INFINITA_SEQUENCE_OPENING"))
        await reset_wall(holder)
        var recall: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")))
        for i in range(12):
            native_travel(holder,phase+"_perception_"+str(i),false)
            await physics_frame
            native_travel(holder,phase+"_memory_"+str(i),true,recall)
            await physics_frame
    var file:=FileAccess.open(OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE"),FileAccess.WRITE)
    file.store_string(FileAccess.get_file_as_string(state_path));file.close()
    print("008EH_NATIVE_PATTERN_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures,"opening_z":opening_z}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
