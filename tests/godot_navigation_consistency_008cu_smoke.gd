extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var Motion = load("res://world_map_local_motion.gd")
    var steep = Motion.new(func(x,_z): return 2.0*(x+80.0))
    var origin := Vector3(-80,0,0)
    var forward: Dictionary = steep._sense_ahead(origin,Vector2(-79,0),null,Vector2(-70,0))
    check(not forward.allowed and forward.reason=="step_too_high","Whole-step rise must be rejected before selecting a perceived free step")
    var lateral: Dictionary = steep._sense_ahead(origin,Vector2(-80,1),null,Vector2(-70,0))
    check(lateral.allowed and lateral.clear_ahead,"A lateral escape must remain available")
    var gentle = Motion.new(func(x,_z): return 0.8*(x+80.0))
    check(gentle._route_connection_clear(Vector2(-80,0),Vector2(-78,0),null),"Two-metre route connection must match two executable one-metre decisions")
    check(not steep._route_connection_clear(Vector2(-80,0),Vector2(-78,0),null),"Planner cannot conceal an excessive executable step")
    var checks := 0
    for rise in [0.0,0.8,1.2,1.4,2.0]:
        var motion = Motion.new(func(x,_z):return float(rise)*(x+80.0))
        for direction in [Vector2.RIGHT,Vector2.LEFT,Vector2.UP,Vector2(1,1).normalized()]:
            for length_m in [0.2,0.5,1.0]:
                var endpoint: Vector2 = Vector2(-80,0)+direction*float(length_m)
                var sensed: Dictionary = motion._sense_ahead(origin,endpoint,null,Vector2(-60,0))
                var executed: Dictionary = motion._traversability.validate_step(origin,Vector3(endpoint.x,0,endpoint.y))
                check(not sensed.allowed or executed.allowed,"An allowed sensed candidate must pass whole-step execution")
                checks += 1
    var flat = Motion.new(func(_x,_z):return 0.0)
    var requested := Vector3(41,0,-20)
    var resolved: Dictionary = flat.resolve_destination(requested)
    check(resolved.allowed and resolved.adjusted,"A river destination must be adjusted locally")
    check(flat._traversability.surface(resolved.position).walkable,"Adjusted destination must be classified walkable")
    check(resolved.position.distance_to(requested)<=16.001,"Destination adjustment must remain bounded")
    var bridge: Dictionary = flat.resolve_destination(Vector3(32,0,-32))
    check(bridge.allowed and not bridge.adjusted,"A destination on the bridge must remain unchanged")
    var commit = load("res://nov_route_goal.gd").new()
    var selected: Vector3 = commit.choose(Vector3(18,0,-20),requested,0.1,"fixture",Callable(flat,"resolve_destination"))
    check(selected==resolved.position and commit.adjusted==1 and commit.active,"Committed goal must use the resolved dry destination")
    check(requested==Vector3(41,0,-20),"Feed coordinates must remain unchanged")
    var denied = Motion.new(func(_x,_z):return 0.0,512.0,func(_x,_z):return {"walkable":false,"surface":"water","reason":"fixture_lake"})
    var waiting = load("res://nov_route_goal.gd").new()
    var stationary: Vector3 = waiting.choose(Vector3(-80,0,0),Vector3(-70,0,0),0.1,"fixture",Callable(denied,"resolve_destination"))
    check(stationary==Vector3(-80,0,0) and not waiting.active and waiting.rejected==1,"An entirely unwalkable neighbourhood cannot create an impossible committed goal")
    var holder := Node3D.new()
    root.add_child(holder)
    var features = load("res://world_map_features.gd").new(func(_x,_z):return 0.0)
    features._bridge(holder)
    var physical = Motion.new(Callable(features,"walk_height"))
    physical._experience = load("res://nov_navigation_experience.gd").new("")
    var body: CharacterBody3D = physical.create_body(holder,null)
    await physics_frame
    var position := Vector3(18,0,-20)
    var physical_goal: Vector3 = physical.resolve_destination(requested).position
    var reached := false
    var collisions := 0
    var water_entries := 0
    var bridge_steps := 0
    for tick in range(3000):
        var result: Dictionary = physical.advance(position,Vector2.ZERO,physical_goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
        position = result.get("position",position)
        collisions += int(result.get("collisions",0))
        var surface: Dictionary = physical._traversability.surface(position)
        if not surface.walkable: water_entries += 1
        if surface.surface=="bridge": bridge_steps += 1
        if result.get("reached",false):
            reached = true
            break
    check(reached and bridge_steps>0,"An adjusted river destination must be reached through the physical bridge")
    check(collisions==0 and water_entries==0,"Destination adjustment must not permit a shortcut through water or rails")
    print("Adjusted physical route reached=",reached," bridge_steps=",bridge_steps," collisions=",collisions," water_entries=",water_entries)
    holder.queue_free()
    await process_frame
    print("Navigation consistency comparisons=",checks," adjusted=",selected)
    print("Navigation consistency smoke: ",failures," failures")
    quit(1 if failures else 0)
