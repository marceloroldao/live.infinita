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
    var space := holder.get_world_3d().direct_space_state
    var corridor := func(a: Vector2,b: Vector2)->bool:
        return motion._route_connection_clear(a,b,space)
    var nav = load("res://nov_navigation_experience.gd").new("")
    nav._observed_route.assign([Vector2(-100,-98),Vector2(-98,-98),Vector2(-96,-98),Vector2(-96,-96)])
    var original: Array[Vector2] = nav._observed_route.duplicate()
    check(nav._observed_shortcut_index(Vector2(-100,-100),corridor)==2,"An unobstructed corner may shorten six metres of observed path")
    check(nav._observed_route==original,"Testing a shortcut cannot discard waypoints before the movement step is accepted")
    nav.route_shortcuts_enabled = false
    check(nav._observed_shortcut_index(Vector2(-100,-100),corridor)==0,"Control run must preserve the original path")
    nav.route_shortcuts_enabled = true
    var obstacle := StaticBody3D.new()
    var shape := CollisionShape3D.new()
    var box := BoxShape3D.new()
    box.size = Vector3(1,4,1)
    shape.shape = box
    obstacle.add_child(shape)
    obstacle.position = Vector3(-98.5,2,-99.5)
    holder.add_child(obstacle)
    await physics_frame
    check(corridor.call(Vector2(-100,-100),Vector2(-100,-98)),"The original first edge must remain physically clear")
    check(nav._observed_shortcut_index(Vector2(-100,-100),corridor)==0,"The complete capsule sweep must reject corner cutting through a solid obstacle")
    obstacle.queue_free()
    await physics_frame
    nav._observed_route.assign([Vector2(20,-8),Vector2(24,-8),Vector2(26,-8)])
    check(nav._observed_shortcut_index(Vector2(18,-8),corridor)==0,"A shortcut cannot cross water even when its endpoints appear nearby")
    var steep = load("res://world_map_local_motion.gd").new(func(x,_z):return (x+100.0)*2.0)
    nav._observed_route.assign([Vector2(-99,-100),Vector2(-98,-100),Vector2(-97,-100)])
    check(nav._observed_shortcut_index(Vector2(-100,-100),func(a,b):return steep._route_connection_clear(a,b,space))==0,"Steep terrain must use the executed step height limit")
    var calls := [0]
    nav._observed_route.assign([Vector2(1,0),Vector2(2,0),Vector2(3,0),Vector2(4,0),Vector2(5,0),Vector2(6,0)])
    nav._observed_shortcut_index(Vector2.ZERO,func(a,b):
        calls[0] += 1
        check(a.distance_to(b)<=6.0,"Each shortcut probe stays within six metres")
        return false)
    check(calls[0]==3,"Rejected shortcuts cannot exceed three full corridor probes per decision")
    var lengths: Array[float] = []
    for enabled in [false,true]:
        motion._experience = load("res://nov_navigation_experience.gd").new("")
        motion._experience.route_shortcuts_enabled = enabled
        var position := Vector3(18,0,-8)
        var goal := Vector3(62,0,-8)
        var reached := false
        var collisions := 0
        var water := 0
        var shortened := 0
        var distance := 0.0
        for tick in range(4000):
            var before := position
            var result: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,space,true,4.0)
            position = result.get("position",position)
            distance += position.distance_to(before)
            collisions += int(result.get("collisions",0))
            if not motion._traversability.surface(position).walkable: water += 1
            if int(motion._experience.decision_evidence.get("observed_route_shortcut_waypoints",0))>0 and position.distance_to(before)>0.001: shortened += 1
            if result.get("reached",false):
                reached = true
                break
        print("Bridge shortcuts=",enabled," reached=",reached," distance=",distance," collisions=",collisions," water=",water," shortened_frames=",shortened)
        check(reached and collisions==0 and water==0,"Both controlled bridge runs must arrive without collisions or water entry")
        if enabled:check(shortened>0,"The improved run must actually execute physically validated shortcuts")
        lengths.append(distance)
    check(lengths[1]<lengths[0]-0.1,"The same physical bridge fixture must have a shorter executed route")
    holder.queue_free()
    await process_frame
    print("Route shortcuts smoke: ",failures," failures")
    quit(1 if failures else 0)
