extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var holder := Node3D.new()
    root.add_child(holder)
    var features = load("res://world_map_features.gd").new(func(_x,_z):return 0.0)
    features._bridge(holder)
    var motion = load("res://world_map_local_motion.gd").new(Callable(features,"walk_height"))
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    for start_z in [-160.0,96.0]:
        motion._experience = load("res://nov_navigation_experience.gd").new("")
        var position := Vector3(18,0,float(start_z))
        var goal := Vector3(62,0,float(start_z))
        var guard = load("res://nov_route_goal.gd").new()
        guard.choose(position,goal,0.0,"physical-fixture")
        var reached := false
        var collisions := 0
        var water := 0
        var frontier_steps := 0
        var return_steps := 0
        var distance := 0.0
        for tick in range(15000):
            var before := position
            var committed: Vector3 = guard.choose(position,goal+Vector3(16,0,0),0.1,"physical-fixture")
            var result: Dictionary = motion.advance(position,Vector2.ZERO,committed,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
            position = result.get("position",position)
            distance += position.distance_to(before)
            collisions += int(result.get("collisions",0))
            if not motion._traversability.surface(position).walkable: water += 1
            var mode: String = motion._experience.decision_evidence.get("observed_route_mode","")
            if mode.begins_with("frontier") and position.distance_to(before)>0.001: frontier_steps += 1
            if mode=="frontier-return" and position.distance_to(before)>0.001: return_steps += 1
            if result.get("reached",false):
                reached = true
                break
        print("Distant bridge z=",start_z," reached=",reached," distance=",distance," frontier_steps=",frontier_steps," return_steps=",return_steps," plans=",motion._experience.route_plan_builds," end=",position)
        check(guard.expired==0 and guard.serial==1 and position.distance_to(goal)<0.1,"Actual distant crossing must retain the original goal despite changed feed proposals")
        check(reached and frontier_steps>0,"A bridge initially 128 m away must be discovered through successive local frontiers")
        if start_z<0:check(return_steps>0,"An initially wrong exploration direction must reverse through the known corridor")
        check(collisions==0 and water==0,"Long exploration must preserve physical collision and water restrictions")
        check(motion._experience.explored_cells.size()<=4096,"Exploration history must stay bounded")
    holder.queue_free()
    await process_frame
    var commit = load("res://nov_route_goal.gd").new()
    commit.choose(Vector3.ZERO,Vector3(1000,0,0),0.1,"fixture")
    for i in range(2700):
        commit.choose(Vector3(0,0,float(i/600)*8.0),Vector3(900,0,0),0.1,"fixture")
    check(commit.serial==1 and commit.expired==0,"Novel executed positions must keep the original goal beyond the old 180-second deadline")
    commit.total_elapsed = 899.95
    commit.choose(Vector3(0,0,40),Vector3(900,0,0),0.1,"fixture")
    check(commit.expired==1,"Novelty cannot bypass the 900-second hard limit")
    var stopped = load("res://nov_route_goal.gd").new()
    stopped.choose(Vector3.ZERO,Vector3(100,0,0),0.1,"fixture")
    for i in range(1810):
        stopped.choose(Vector3.ZERO,Vector3(200,0,0),0.1,"fixture")
    check(stopped.expired==1,"Stationary exploration still expires after 180 seconds")
    var oscillating = load("res://nov_route_goal.gd").new()
    oscillating.choose(Vector3.ZERO,Vector3(100,0,0),0.1,"fixture")
    for i in range(2000):
        oscillating.choose(Vector3(float(i%2)*8.0,0,0),Vector3(200,0,0),0.1,"fixture")
    check(oscillating.expired==1,"Repeated visits to the same two cells cannot indefinitely renew the goal")
    print("Frontier routes smoke: ",failures," failures")
    quit(1 if failures else 0)
