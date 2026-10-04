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
    motion._experience = load("res://nov_navigation_experience.gd").new("")
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var position := Vector3(18,0,-8)
    position.y = features.walk_height(position.x,position.z)
    var goal := Vector3(62,0,-8)
    var reached := false
    var water_entries := 0
    var collisions := 0
    var distance := 0.0
    for tick in range(3000):
        var previous := position
        var result: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
        position = result.get("position",position)
        distance += position.distance_to(previous)
        collisions += int(result.get("collisions",0))
        if not motion._traversability.surface(position).get("walkable",false): water_entries += 1
        if result.get("reached",false):
            reached = true
            break
    check(reached,"Observed route must discover and cross the physical bridge")
    check(water_entries==0 and collisions==0,"Crossing cannot enter river or pass through rails")
    check(motion._experience.route_plan_builds>0,"Crossing must use observed route inference")
    print("Observed bridge reached=",reached," distance=",distance," collisions=",collisions," plans=",motion._experience.route_plan_builds," last_plan_ms=",motion._experience._route_search.elapsed_ms)
    holder.queue_free()
    await process_frame
    var planner = load("res://nov_observed_route.gd").new()
    # A different opening checks that no bridge coordinates are programmed into inference.
    var moved_opening := func(a: Vector2,b: Vector2) -> bool:
        if a.x<0 and b.x>=0 or b.x<0 and a.x>=0:
            return a.y>=8 and a.y<=12 and b.y>=8 and b.y<=12
        return true
    var route: Array[Vector2] = planner.build(Vector2(-6,0),Vector2(6,0),moved_opening)
    check(not route.is_empty() and route[-1].distance_to(Vector2(6,0))<0.1,"Relocated opening must be inferred from probes")
    var previous := Vector2(-6,0)
    for point in route:
        check(moved_opening.call(previous,point),"Every planned connection must be observed traversable")
        previous = point
    print("Observed crossing smoke: ",failures," failures")
    quit(1 if failures else 0)
