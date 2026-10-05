extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var Planner = load("res://nov_observed_route.gd")
    var planner = Planner.new()
    var goal := Vector2(4.7,0.7)
    var exact_checks := [0]
    var route: Array[Vector2] = planner.build(Vector2.ZERO,goal,func(a,b):
        if b.distance_to(goal)<0.001:
            exact_checks[0] += 1
            return a==Vector2(2,0)
        return true,{},Vector2.LEFT,true)
    check(planner.mode=="goal" and route[-1]==goal,"A sensed exact off-grid goal overrides frontier return")
    check(exact_checks[0]>0,"The last corridor must actually be probed")
    var covered := {}
    for x in range(-5,6):
        for z in range(-5,6):covered[Vector2i(x,z)]=true
    var blocked_goal := Vector2(2.5,0.5)
    route = planner.build(Vector2.ZERO,blocked_goal,func(_a,b):return b.distance_to(blocked_goal)>0.001,covered)
    check(planner.mode=="none" and route.is_empty(),"A covered endpoint near an unconnected goal cannot repeatedly count as fresh progress")
    route = planner.build(Vector2.ZERO,blocked_goal,func(_a,_b):return true,covered)
    check(planner.mode=="goal" and route[-1]==blocked_goal,"A genuinely connected goal remains reachable even inside visited coverage")
    route = planner.build(Vector2.ZERO,Vector2(33,0.5),func(_a,_b):return true)
    check(planner.mode!="goal","The final connector cannot extend perception beyond the local planning window")
    for point in route:
        check(absf(point.x)<=32.0 and absf(point.y)<=32.0,"All planned waypoints remain inside the observed window")
    var holder := Node3D.new()
    root.add_child(holder)
    var Motion = load("res://world_map_local_motion.gd")
    var motion = Motion.new(func(_x,_z):return 0.0)
    motion._experience = load("res://nov_navigation_experience.gd").new("")
    var body: CharacterBody3D = motion.create_body(holder,null)
    var tree := StaticBody3D.new()
    var shape := CollisionShape3D.new()
    var cylinder := CylinderShape3D.new()
    cylinder.radius = 0.8
    cylinder.height = 4
    shape.shape = cylinder
    tree.add_child(shape)
    tree.position = Vector3(-80,2,0)
    holder.add_child(tree)
    await physics_frame
    var requested := Vector3(-80,0,0)
    var resolved: Dictionary = motion.resolve_destination(requested)
    var space := holder.get_world_3d().direct_space_state
    check(resolved.allowed and resolved.adjusted,"A destination inside a trunk must be adjusted before commitment")
    check(motion._destination_clear(resolved.position,space),"Adjusted destination must fit the actual body capsule")
    check(resolved.position.distance_to(requested)<=16.001,"Body clearance adjustment remains bounded")
    check(requested==Vector3(-80,0,0),"The feed destination must remain unchanged")
    var guard = load("res://nov_route_goal.gd").new()
    var position := Vector3(-88,0,0)
    var selected: Vector3 = guard.choose(position,requested,0.1,"fixture",Callable(motion,"resolve_destination"))
    check(guard.adjusted==1 and selected==resolved.position,"Commitment must use the physically free destination")
    var reached := false
    var collisions := 0
    var distance := 0.0
    for tick in range(3000):
        var before := position
        var result: Dictionary = motion.advance(position,Vector2.ZERO,selected,0.1,body,space,true,4.0)
        position = result.get("position",position)
        distance += position.distance_to(before)
        collisions += int(result.get("collisions",0))
        check(motion._destination_clear(position,space),"Executed approach must never overlap the trunk")
        if result.get("reached",false):
            reached = true
            break
    check(reached and collisions==0,"Nov must detour around the physical trunk and reach the resolved goal")
    print("Occupied destination reached=",reached," distance=",distance," collisions=",collisions," adjusted=",selected)
    var sealed := StaticBody3D.new()
    var sealed_shape := CollisionShape3D.new()
    var box := BoxShape3D.new()
    box.size = Vector3(40,4,40)
    sealed_shape.shape = box
    sealed.add_child(sealed_shape)
    sealed.position = Vector3(-160,2,0)
    holder.add_child(sealed)
    await physics_frame
    var rejected: Dictionary = motion.resolve_destination(Vector3(-160,0,0))
    check(not rejected.allowed,"No free endpoint within sixteen metres must reject the destination")
    holder.queue_free()
    await process_frame
    var slope_holder := Node3D.new()
    root.add_child(slope_holder)
    var slope = Motion.new(func(x,_z):return 0.8*(x+80))
    slope._experience = load("res://nov_navigation_experience.gd").new("")
    var slope_body: CharacterBody3D = slope.create_body(slope_holder,null)
    await physics_frame
    position = Vector3(-80,0,0)
    var slope_goal := Vector3(-77.4,2.08,0)
    reached = false
    collisions = 0
    for tick in range(200):
        var result: Dictionary = slope.advance(position,Vector2.ZERO,slope_goal,0.1,slope_body,slope_holder.get_world_3d().direct_space_state,true,4.0)
        position = result.get("position",position)
        collisions += int(result.get("collisions",0))
        if result.get("reached",false):
            reached = true
            break
    check(reached and collisions==0,"A segmented executable uphill corridor must reach an off-grid goal without relaxing the step limit")
    slope_holder.queue_free()
    await process_frame
    print("Goal approach smoke: ",failures," failures")
    quit(1 if failures else 0)
