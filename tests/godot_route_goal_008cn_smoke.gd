extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var Goal = load("res://nov_route_goal.gd")
    var goal = Goal.new()
    var first := Vector3(6,0,0)
    check(goal.choose(Vector3.ZERO,first,0.1,"a")==first,"Commit observed destination")
    var identity: String = goal.identity()
    check(goal.choose(Vector3(1,0,0),Vector3(30,0,10),0.1,"a")==first,"Feed updates must preserve destination")
    check(goal.identity()==identity,"Route identity must stay stable")
    check(goal.choose(first,Vector3(30,0,10),0.1,"a")==Vector3(30,0,10),"Arrival acquires next observed destination")
    check(goal.completed==1 and goal.identity()!=identity,"Arrival counted once")
    goal.choose(Vector3(30,0,10),Vector3(30,0,10),0.1,"a")
    goal.choose(Vector3(30,0,10),Vector3(30,0,10),0.1,"a")
    check(goal.completed==2 and not goal.active,"Stationary feed must not create repeated arrivals")
    goal.choose(Vector3.ZERO,first,0.1,"a")
    check(goal.choose(Vector3.ZERO,Vector3(9,0,9),0.1,"b")==Vector3(9,0,9),"New world resets committed goal")
    goal.elapsed = goal.MAX_SECONDS-0.01
    check(goal.choose(Vector3.ZERO,first,0.1,"b")==first and goal.expired==1,"Timeout reassesses latest destination")
    goal.reset()
    goal.choose(Vector3.ZERO,Vector3(INF,0,0),0.1,"b")
    check(not goal.active,"Nonfinite destination cannot be committed")

    var Experience = load("res://nov_navigation_experience.gd")
    var experience = Experience.new("")
    var clear := func(_point: Vector2) -> Dictionary: return {"allowed":true,"clear_ahead":true}
    var pending: Vector2 = experience.target(Vector2.ZERO,Vector2(5,0),clear)
    var serial: int = experience.decision_serial
    experience.apply_recall({"entries":[{"kind":"successful_route_step","key":"5,0|0,0","to":[0.0,1.0],"observation_id":"structural-event:"+"a".repeat(40)}]})
    check(experience.target(Vector2(0.2,0),Vector2(5,0),clear)==pending and experience.decision_serial==serial,"Recall refresh cannot cancel physical step")
    experience.apply_recall({})
    check(experience.recalled_routes.is_empty() and experience.active,"Expired evidence clears without interrupting current step")
    experience.arrived(Vector2(5,0))
    check(not experience.active,"Actual arrival releases step")

    var stage := Node3D.new()
    root.add_child(stage)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z): return 0.0)
    motion._experience = Experience.new("")
    var body: CharacterBody3D = motion.create_body(stage,null)
    for item in [[Vector3(-97.5,1,0),Vector3(0.2,2,5)],[Vector3(-100.5,1,-2.5),Vector3(6.2,2,0.2)],[Vector3(-100.5,1,2.5),Vector3(6.2,2,0.2)]]:
        var wall := StaticBody3D.new()
        wall.position = item[0]
        var collision := CollisionShape3D.new()
        var box := BoxShape3D.new()
        box.size = item[1]
        collision.shape = box
        wall.add_child(collision)
        stage.add_child(wall)
    await physics_frame
    var position := Vector3(-100,0,0)
    var destination := Vector3(-94,0,0)
    var committed = Goal.new()
    committed.choose(position,destination,0.1,"fixture")
    var collisions := 0
    var arrived := false
    for tick in range(300):
        var latest := Vector3(-140,0,40) if tick%2 else Vector3(-70,0,-40)
        var target: Vector3 = committed.choose(position,latest,0.1,"fixture")
        check(target==destination,"Changing feed cannot replace active U route")
        motion.route_goal_id = committed.identity()
        var result: Dictionary = motion.advance(position,Vector2.ZERO,target,0.1,body,stage.get_world_3d().direct_space_state,true,8.0)
        position = result["position"]
        collisions += int(result.get("collisions",0))
        if Vector2(position.x,position.z).distance_to(Vector2(destination.x,destination.z))<0.1:
            arrived = true
            break
        await physics_frame
    check(arrived,"Physical U route reaches original destination despite changing feed")
    check(collisions==0,"U route avoids physical collisions")
    print("Stable route fixture position=",position," collisions=",collisions," arrived=",arrived)
    stage.queue_free()
    await process_frame
    var preview = load("res://world_map_preview.tscn").instantiate()
    root.add_child(preview)
    preview.set_process(false)
    await process_frame
    var feed = preview.get_node_or_null("LiveFeed")
    if feed != null:
        feed.enabled = false
        feed.set_process(false)
    preview._position = Vector3(-160,float(preview._features.call("walk_height",-160.0,-32.0)),-32)
    preview._last_live_position = preview._position + Vector3(2,0,0)
    preview._live_walk_velocity = Vector2.ZERO
    var initial_goal: Vector3 = preview._last_live_position
    preview._advance_live_walk(0.05)
    var route_id: String = preview._local_motion.route_goal_id
    preview._last_live_position = initial_goal + Vector3(100,0,100)
    preview._local_motion._experience.apply_recall({})
    preview._advance_live_walk(0.05)
    check(preview._route_goal.goal==initial_goal,"Live scene keeps observed local goal")
    check(preview._local_motion.route_goal_id==route_id and not route_id.is_empty(),"Live scene forwards stable route identity")
    preview.queue_free()
    await process_frame
    print("Stable route goal smoke: ",failures," failures")
    quit(1 if failures else 0)
