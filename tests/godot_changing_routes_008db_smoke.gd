extends SceneTree
var failures := 0
var completed: Array = []
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize():call_deferred("run")
func wall(parent: Node3D) -> StaticBody3D:
    var node := StaticBody3D.new()
    var collision := CollisionShape3D.new()
    collision.shape = BoxShape3D.new()
    node.add_child(collision)
    parent.add_child(node)
    return node
func configure(node: StaticBody3D,min_z: float,max_z: float) -> void:
    node.get_child(0).shape.size = Vector3(0.4,4,max_z-min_z)
    node.position = Vector3(-80,2,(min_z+max_z)*0.5)
func travel(motion,body: CharacterBody3D,holder: Node3D,start: Vector3,goal: Vector3,label: String) -> Dictionary:
    var position := start
    var reached := false
    var collisions := 0
    var length := 0.0
    for tick in range(4000):
        var before := position
        var result: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
        position = result.get("position",position)
        collisions += int(result.get("collisions",0))
        length += position.distance_to(before)
        if result.get("reached",false):
            reached = true
            break
    check(reached and collisions==0,label+": must reach the unchanged goal without collisions")
    print("Changing route ",label," reached=",reached," distance=",length," collisions=",collisions," plans=",motion._experience.route_plan_builds," revisions=",motion._experience.route_revision_count)
    return {"position":position,"reached":reached,"distance":length}
func run():
    var holder := Node3D.new()
    root.add_child(holder)
    var lower := wall(holder)
    var upper := wall(holder)
    configure(lower,-92,-82)
    configure(upper,-78,-68)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    motion._experience = load("res://nov_navigation_experience.gd").new("")
    motion._episodes = load("res://nov_navigation_episodes.gd").new("")
    motion._experience.working_memory.storage = ""
    motion._episodes.action_completed.connect(Callable(motion._experience.working_memory,"observe_completed"))
    motion._episodes.action_completed.connect(func(a):completed.append(a.duplicate(true)))
    var context := {"world_id":"changing-physical-fixture","observer_entity_id":"nov","world_sequence":1,"runtime_position":{"x":0.0,"y":0.0}}
    motion._episodes.set_context(context)
    motion._episodes.enabled = true
    motion._experience.working_memory.set_context(context)
    motion._experience.working_memory.enabled = true
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var goal := Vector3(-68,0,-80)
    travel(motion,body,holder,Vector3(-86,0,-80),goal,"original opening")
    var memory = motion._experience.working_memory
    var old_key: String = memory.address([-68.0,-80.0],[-81.0,-80.0])
    check(memory.entries.has(old_key),"The original route must populate RAM through real completed movements")
    var old_to: Array = memory.entries[old_key].to.duplicate()
    motion._experience.reset_route_plan()
    motion._experience.active = false
    var partial: Dictionary = motion.advance(Vector3(-81,0,-80),Vector2.ZERO,goal,0.05,body,holder.get_world_3d().direct_space_state,true,4.0)
    var current: Vector3 = partial.position
    check(motion._experience.active,"The map change must occur during an unfinished physically checked step")
    # Mimic a recent plan: contradiction must override the old five-second throttle.
    motion._experience._route_search_origin = Vector2(current.x,current.z)
    motion._experience._route_search_at = Time.get_ticks_msec()
    var cached_nav = load("res://nov_navigation_experience.gd").new("")
    cached_nav.last_goal = Vector2(goal.x,goal.z)
    var corridor := func(a,b):return motion._route_connection_clear(a,b,holder.get_world_3d().direct_space_state)
    cached_nav._observed_route = cached_nav._route_search.build(Vector2(-81,-80),Vector2(goal.x,goal.z),corridor)
    check(not cached_nav._observed_route.is_empty(),"The cached route must first be physically verified in the old geometry")
    configure(lower,-92,-76)
    configure(upper,-72,-68)
    await physics_frame
    check(motion._destination_clear(current,holder.get_world_3d().direct_space_state),"Moving the wall must leave the actual starting body free")
    var cache_start := Vector2(-81,-80)
    var sensed := func(p):return motion._sense_ahead(Vector3(-81,0,-80),p,holder.get_world_3d().direct_space_state,Vector2(goal.x,goal.z))
    var cache_result: Vector2 = cached_nav.target(cache_start,Vector2(goal.x,goal.z),sensed,corridor)
    check(cache_result==cache_start and not cached_nav.active and cached_nav.route_revision_count==1,"A changed cached path must pause and be discarded before execution")
    check(cached_nav.failures.is_empty() and cached_nav.attempts==0,"A rejected cached plan is perception, not an executed failure")
    cached_nav.target(cache_start,Vector2(goal.x,goal.z),sensed,corridor)
    check(cached_nav.route_plan_builds==1,"Discarding a stale cached route must permit immediate rebuilding")
    var before_plans: int = motion._experience.route_plan_builds
    motion.advance(current,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
    check(motion._experience.route_revision_count==1,"The newly blocked pending passage must trigger one observed revision")
    check(motion._experience.route_plan_builds>before_plans,"A changed passage must trigger immediate planning despite a recent search")
    check(not memory.entries.has(old_key),"Contradicted RAM recommendation must be invalidated before another movement")
    var first_new_action := completed.size()
    travel(motion,body,holder,current,goal,"new opening")
    check(memory.entries.has(old_key) and memory.entries[old_key].to!=old_to,"The new executed escape must replace the contradicted RAM candidate")
    var revised_success := false
    for a in completed.slice(first_new_action):
        if a.outcome in ["step_reached","goal_reached"] and a.perception.has("route_revision"):
            revised_success = true
    check(revised_success,"Changed-path evidence must accompany an actual successfully executed decision")
    check(memory.promoted.is_empty(),"Discovery alone must not manufacture three causal reuses or durable learning")
    configure(lower,-92,-82)
    configure(upper,-78,-68)
    await physics_frame
    motion._experience.active = false
    motion._experience.reset_route_plan()
    travel(motion,body,holder,Vector3(-86,0,-80),goal,"original opening restored")
    var blocked := 0
    for a in completed:
        if a.outcome=="blocked":blocked += 1
    check(blocked==0,"Sensed contradictions cannot fabricate failed physical attempts")
    check(memory.entries.size()<=512,"Changed-map experience remains bounded")
    holder.queue_free()
    await process_frame
    # Invalidating a recommendation must preserve old historical promotions.
    var historical = load("res://nov_navigation_working_memory.gd").new("")
    historical.entries["fixture"]={"to":[1,0]}
    historical.promoted["fixture"]={"historical":true}
    historical.invalidate_candidate("fixture")
    check(historical.entries.is_empty() and historical.promoted.has("fixture"),"A new obstacle cannot erase historical promotion evidence")
    historical.enabled = true
    historical.entries["5,0|0,0"]={"to":[0,1],"last_ms":Time.get_ticks_msec()}
    var guarded = load("res://nov_navigation_experience.gd").new("")
    guarded.working_memory = historical
    var safe: Vector2 = guarded.target(Vector2.ZERO,Vector2(5,0),func(p):return {"allowed":p.y<0.5,"clear_ahead":p.y<0.5})
    check(safe==Vector2(1,0) and not historical.entries.has("5,0|0,0"),"A contradicted RAM candidate must also be removed during ordinary candidate selection")
    check(historical.promoted.has("fixture"),"Rejection during selection must preserve historical evidence")
    print("Changing routes smoke: ",failures," failures")
    quit(1 if failures else 0)
