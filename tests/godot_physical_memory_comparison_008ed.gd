extends SceneTree
# Real capsules and physical probes in an isolated fixed wall/gap fixture.
var failures := 0
var runs: Array = []
var initial := Vector3(-86,0,-80)
var destination := Vector3(-68,0,-80)
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func _initialize() -> void:call_deferred("run")
func flat(_x: float,_z: float) -> float:return 0.0
func new_memory():
    var memory = load("res://nov_navigation_working_memory.gd").new("")
    memory.world_id="physical-benchmark-008ed"
    return memory
func make_motion(memory):
    var motion = load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion._experience=load("res://nov_navigation_experience.gd").new("")
    motion._experience.working_memory=memory
    motion._experience.trial_error_enabled=true
    motion._experience.memoria_enabled=false
    motion._episodes=load("res://nov_navigation_episodes.gd").new("")
    motion._episodes.enabled=true
    motion._episodes.set_context({"world_id":"physical-benchmark-008ed","observer_entity_id":"nov"})
    motion._journey=load("res://nov_navigation_journey.gd").new(memory)
    motion._episodes.action_completed.connect(Callable(memory,"observe_completed"))
    motion._episodes.action_completed.connect(Callable(motion._journey,"observe_completed"))
    return motion
func wall(parent: Node3D,low: float,high: float) -> void:
    var body := StaticBody3D.new()
    var shape := CollisionShape3D.new()
    var box := BoxShape3D.new()
    box.size=Vector3(0.4,4,high-low)
    shape.shape=box
    body.add_child(shape);parent.add_child(body)
    body.position=Vector3(-80,2,(low+high)*0.5)
func travel(holder: Node3D,memory,label: String,recall: Dictionary = {}) -> Dictionary:
    var motion = make_motion(memory)
    if not recall.is_empty():
        motion._experience.memoria_enabled=true
        motion._experience.apply_recall(recall)
    motion.route_goal_id="physical-benchmark-008ed:"+label
    var body: CharacterBody3D=motion.create_body(holder,null)
    var current := initial
    var collisions := 0
    var ticks := 0
    var crossed := false
    var last_serial := -1
    var ram_agreements := 0
    var core_agreements := 0
    var started := Time.get_ticks_msec()
    for i in range(2500):
        var old := current
        var value: Dictionary=motion.advance(current,Vector2.ZERO,destination,0.1,body,holder.get_world_3d().direct_space_state,true,4)
        current=value.get("position",current)
        if motion._experience.decision_serial!=last_serial:
            last_serial=motion._experience.decision_serial
            if motion._experience.last_decision_source=="perception-working-memory-agreement":ram_agreements+=1
            if motion._experience.last_decision_source=="perception-memory-agreement":core_agreements+=1
        collisions+=int(value.get("collisions",0));ticks+=1
        if old.x < -80 and current.x>=-80:
            crossed = absf(current.z+30)<=2.0 or absf(current.z)>180.5
        if bool(value.get("reached",false)):break
    var arrived := Vector2(current.x,current.z).distance_to(Vector2(destination.x,destination.z))<0.1
    if not arrived:motion._journey.abort("limite do experimento","interrupted")
    var result := {"arm":label,"arrived":arrived,"ticks":ticks,"simulated_seconds":ticks*0.1,
        "compute_wall_ms":Time.get_ticks_msec()-started,"distance_m":motion._journey.distance_m,
        "collisions":collisions,"causal_ram_steps":motion._journey.causal_ram_steps,
        "causal_memoria_steps":motion._journey.causal_memoria_steps,
        "route_plan_builds":motion._experience.route_plan_builds,"physically_open_crossing":crossed,
        "ram_agreement_decisions":ram_agreements,"core_agreement_decisions":core_agreements,
        "verified_recalled_routes_loaded":motion._experience.recalled_routes.size()}
    check(arrived and collisions==0 and crossed,label+": physical capsule must arrive without crossing wall")
    check(motion._experience.route_plan_builds==0,label+": no global route search")
    if label=="verified_core_recall":
        check(motion._experience.recalled_routes.size()>0 and core_agreements>0,
            "Verified core data must actually participate in physical route decisions")
    # The reference evidence is the first complete, collision-free physical journey.
    if label=="training":
        var rows: Array=[]
        for step in motion._journey.steps:
            var address: String=step.address
            var parts=address.split("|")
            var from=parts[1].split(",")
            var goal=parts[0].split(",")
            rows.append({"kind":"successful_route_step","key":address,
                "from":[float(from[0]),float(from[1])],"goal":[float(goal[0]),float(goal[1])],
                "to":step.to,"route_quality":memory.observed_quality(address,Vector2(step.to[0],step.to[1]))})
        var path:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE")
        if not path.is_empty():
            var file:=FileAccess.open(path,FileAccess.WRITE)
            check(file!=null,"Fixture file can be written")
            if file!=null:
                file.store_string(JSON.stringify({"schema":"live-infinita-physical-memory-fixture/v1",
                    "scope":"isolated_real_capsule_fixture","world_id":"physical-benchmark-008ed",
                    "run":result,"rows":rows,"promotion_gate_bypassed_for_isolated_transport_test":true,
                    "production_learning_demonstrated":false}));file.close()
    runs.append(result)
    print("008ED_PHYSICAL_RUN "+JSON.stringify(result))
    body.queue_free()
    return result
func run() -> void:
    var holder:=Node3D.new();root.add_child(holder)
    wall(holder,-180,-32);wall(holder,-28,180)
    await physics_frame
    var baseline_memory=new_memory()
    baseline_memory.enabled=false
    var baseline: Dictionary=travel(holder,baseline_memory,"perception")
    await physics_frame
    var memory=new_memory();memory.enabled=true
    var training: Dictionary=travel(holder,memory,"training")
    check(absf(baseline.distance_m-training.distance_m)<0.01 and baseline.ticks==training.ticks,
        "Empty RAM training must reproduce baseline before any recommendation")
    await physics_frame
    for i in range(3):
        travel(holder,memory,"ram_repeat_"+str(i+1))
        await physics_frame
    var recall_path:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")
    if not recall_path.is_empty():
        var recall=JSON.parse_string(FileAccess.get_file_as_string(recall_path))
        check(typeof(recall)==TYPE_DICTIONARY and not recall.get("entries",[]).is_empty(),"Verified core recall fixture required")
        if typeof(recall)==TYPE_DICTIONARY:
            var cold_memory=new_memory();cold_memory.enabled=false
            travel(holder,cold_memory,"verified_core_recall",recall)
            await physics_frame
    print("008ED_PHYSICAL_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures,
        "same_start_goal_obstacles":true,"speed_mps":4,"dt_seconds":0.1,
        "scope":"isolated_real_capsule_fixture","production_learning_demonstrated":false}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
