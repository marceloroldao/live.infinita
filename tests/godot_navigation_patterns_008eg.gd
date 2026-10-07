extends "godot_physical_memory_comparison_008ed.gd"
# Physical situation/action/outcome experiment, with fixed policy in all arms.
var training_rows: Array = []
func pattern_travel(holder: Node3D, patterns, label: String, side: int=0) -> Dictionary:
    var memory=new_memory();memory.enabled=false
    var motion=make_motion(memory)
    motion._experience.contour.pattern_memory=patterns
    motion._experience.contour.exploration_side=side
    motion.route_goal_id="physical-pattern-008eg:"+label
    var body: CharacterBody3D=motion.create_body(holder,null)
    var current:=initial
    var ticks:=0
    var collisions:=0
    var contact: Dictionary={}
    var watchdog=load("res://nov_stuck_recovery.gd").new()
    var rescues:=0
    for i in range(2500):
        var value: Dictionary=motion.advance(current,Vector2.ZERO,destination,0.1,body,holder.get_world_3d().direct_space_state,true,4)
        current=value.get("position",current)
        collisions+=int(value.get("collisions",0));ticks+=1
        if contact.is_empty() and motion._experience.contour.starts>0:
            contact=motion._experience.contour.evidence()
        if watchdog.observe(current,destination,0.1,true):rescues+=1;break
        if bool(value.get("reached",false)):break
    var arrived:=Vector2(current.x,current.z).distance_to(Vector2(destination.x,destination.z))<0.1
    if not arrived:motion._journey.abort("limite ou resgate do experimento","stuck_recovery" if rescues else "interrupted")
    var row: Dictionary={"arm":label,"arrived":arrived,"ticks":ticks,"simulated_seconds":ticks*0.1,
        "distance_m":motion._journey.distance_m,"collisions":collisions,"rescues":rescues,
        "context":contact.get("pattern_context",""),"side":contact.get("initial_side",0),
        "default_side":contact.get("default_side",0),"recommendation":contact.get("pattern_recommendation",{}),
        "pattern_changed_initial_side":contact.get("pattern_changed_initial_side",false),
        "route_plan_builds":motion._experience.route_plan_builds,
        "start":[initial.x,initial.z],"goal":[destination.x,destination.z]}
    check(arrived and collisions==0 and rescues==0,label+": complete collision-free actual journey")
    check(motion._experience.route_plan_builds==0,label+": no global route oracle")
    runs.append(row)
    print("008EG_PATTERN_RUN "+JSON.stringify(row))
    body.queue_free()
    return row
func reset_walls(holder: Node3D) -> void:
    for child in holder.get_children():child.queue_free()
    await physics_frame
    wall(holder,-180,opening_z-2);wall(holder,opening_z+2,180)
    await physics_frame
func run() -> void:
    var holder:=Node3D.new();root.add_child(holder)
    opening_z=-130
    await reset_walls(holder)
    var trained=load("res://nov_navigation_patterns.gd").new()
    # Explore both actions explicitly before recommending one: no gap label
    # or hand-authored preferred action is passed to the learner.
    for side in [1,-1,1,-1]:
        var label: String="train_"+str(training_rows.size())
        var measured: Dictionary=pattern_travel(holder,trained,label,side)
        await physics_frame
        var observation: Dictionary={"attempt_id":label,"context":measured.context,"side":measured.side,
            "outcome":"arrived","distance_m":measured.distance_m,
            "initial_remaining_m":initial.distance_to(destination),
            "physical_attempt":true,"contains_prediction":false,
            "measurement":measured.duplicate(true)}
        check(trained.observe_attempt(observation),"Measured physical training accepted")
        training_rows.append(observation)
    var fixture_path:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE")
    if not fixture_path.is_empty():
        var file:=FileAccess.open(fixture_path,FileAccess.WRITE)
        file.store_string(JSON.stringify({"schema":"live-infinita-pattern-fixture/v1",
            "scope":"isolated_actual_journeys_pattern_evidence","rows":training_rows,
            "promotion_gate_bypassed_for_isolated_transport_test":true}))
        file.close()
    # Changed start AND goal, translated gap; no exact route/address reuse.
    initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60);opening_z=-110
    await reset_walls(holder)
    var empty=load("res://nov_navigation_patterns.gd").new()
    var baseline: Dictionary=pattern_travel(holder,empty,"perception")
    await physics_frame
    trained.enabled=true
    var warm: Dictionary=pattern_travel(holder,trained,"ram_patterns")
    await physics_frame
    check(warm.context==training_rows[0].context,"Observed relative pattern matches after translation and changed goal")
    check(warm.pattern_changed_initial_side and warm.distance_m<baseline.distance_m,"Learned pattern changes action and reduces physical route cost")
    var recall_path:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")
    if not recall_path.is_empty():
        var recall=JSON.parse_string(FileAccess.get_file_as_string(recall_path))
        var recovered=load("res://nov_navigation_patterns.gd").new()
        for row in recall.get("entries",[]):
            check(recovered.observe_attempt(row),"Actual recovered observations accepted")
        recovered.enabled=true
        var cold: Dictionary=pattern_travel(holder,recovered,"verified_core_patterns")
        await physics_frame
        check(cold.pattern_changed_initial_side and cold.distance_m<baseline.distance_m,"Reopened core patterns causally improve held-out journey")
        check(not cold.recommendation.get("observation_ids",[]).is_empty(),"Decision references recovered core provenance")
        check(absf(cold.distance_m-warm.distance_m)<0.01,"Core transport preserves RAM evidence policy")
    # Identical local signature, opening now on the opposite remote side.
    # This must expose stale preference, not claim an unobservable prediction.
    opening_z=-10
    await reset_walls(holder)
    var mirror_baseline: Dictionary=pattern_travel(holder,empty,"mirror_perception")
    await physics_frame
    var mirror_stale: Dictionary=pattern_travel(holder,trained,"mirror_stale_patterns")
    await physics_frame
    check(mirror_stale.context==mirror_baseline.context,"Mirrored remote gap is locally indistinguishable")
    check(mirror_stale.distance_m>mirror_baseline.distance_m,"Expose harmful stale pattern instead of hiding regression")
    for side in [1,-1,1,-1,1,-1,1,-1,1,-1,1,-1]:
        var label: String="changed_training_"+str(trained.records.size())
        var measured: Dictionary=pattern_travel(holder,trained,label,side)
        await physics_frame
        check(trained.observe_attempt({"attempt_id":label,"context":measured.context,"side":measured.side,
            "outcome":"arrived","distance_m":measured.distance_m,"initial_remaining_m":initial.distance_to(destination),
            "physical_attempt":true,"contains_prediction":false}),"Changed physical cost accepted without erasing contradiction")
    var adapted: Dictionary=pattern_travel(holder,trained,"mirror_updated_patterns")
    await physics_frame
    check(adapted.side==1 and int(adapted.recommendation.get("side",0))==1 and absf(adapted.distance_m-mirror_baseline.distance_m)<0.01,"New actual outcomes can overturn stale preference")
    print("008EG_PATTERN_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures,
        "scope":"isolated_actual_journeys_pattern_evidence","production_learning_demonstrated":false}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
