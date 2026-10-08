extends SceneTree
var failures := 0
var gap_z := -30.0
func check(ok: bool,label: String) -> void:
    if not ok:push_error(label);failures+=1
func _initialize() -> void:call_deferred("run")
func flat(_x: float,_z: float) -> float:return 0.0
func wall(parent: Node3D) -> StaticBody3D:
    var node := StaticBody3D.new()
    var shape := CollisionShape3D.new()
    shape.shape = BoxShape3D.new()
    node.add_child(shape);parent.add_child(node)
    return node
func configure(node: StaticBody3D,low: float,high: float) -> void:
    node.get_child(0).shape.size=Vector3(0.4,4,high-low)
    node.position=Vector3(-80,2,(low+high)*0.5)
func travel(motion,body: CharacterBody3D,holder: Node3D,label: String) -> Dictionary:
    var current := Vector3(-86,0,-80)
    var goal := Vector3(-68,0,-80)
    var collisions := 0
    var steps := 0
    var crossed_gap := false
    for tick in range(2500):
        var old := current
        var result: Dictionary = motion.advance(current,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4)
        current=result.get("position",current)
        collisions+=int(result.get("collisions",0));steps+=1
        if old.x < -80 and current.x>=-80:
            crossed_gap=absf(current.z-gap_z)<=2.0 or absf(current.z)>180.5
        if result.get("reached",false):break
    var reached := Vector2(current.x,current.z).distance_to(Vector2(goal.x,goal.z))<0.1
    check(reached,label+": local trial/error must reach goal")
    check(collisions==0,label+": no physical collisions")
    check(crossed_gap,label+": cross only a physically open exit (gap or wall end)")
    print("Contour fixture ",label," reached=",reached," steps=",steps," collisions=",collisions," final=",current)
    return {"reached":reached,"steps":steps}
func run() -> void:
    var policy = load("res://nov_navigation_contour.gd").new()
    var rows: Array[Dictionary]=[
        {"point":Vector2(0,1),"source":"perception","clear_ahead":true},
        {"point":Vector2(0,-1),"source":"memoria.ia","clear_ahead":true}]
    policy.filter(Vector2.ZERO,Vector2(10,0),rows,false)
    check(policy.active and policy.heading.y>0.5,"Remembered bonus must not set the initial contour side")
    policy.filter(Vector2(-1,1),Vector2(10,0),rows,true)
    check(policy.active,"A clear ray obtained only by retreat must not immediately replay the same wall")
    # Candidates must be local to the moved position, rather than stale origin points.
    rows=[{"point":Vector2(5,1),"source":"perception","clear_ahead":true}]
    policy.filter(Vector2(4,1),Vector2(10,0),rows,true)
    check(not policy.active,"A physically clear corridor after forward progress releases contour")
    var rejected = load("res://nov_navigation_experience.gd").new("")
    rejected.trial_error_enabled=true
    var idle: Vector2=rejected.target(Vector2.ZERO,Vector2(10,0),func(_point):return {"allowed":false,"clear_ahead":false})
    check(idle==Vector2.ZERO and not rejected.active,"No observed passage means no forced movement")
    check(rejected.attempts==0 and rejected.failures.is_empty(),"Sensed rejection must not invent executed failure")
    var holder := Node3D.new();root.add_child(holder)
    var lower := wall(holder);var upper := wall(holder)
    configure(lower,-180,gap_z-2);configure(upper,gap_z+2,180)
    var motion = load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion._experience=load("res://nov_navigation_experience.gd").new("")
    motion._experience.working_memory.storage=""
    motion._experience.trial_error_enabled=true
    motion._episodes.storage=""
    var body: CharacterBody3D=motion.create_body(holder,null)
    await physics_frame
    travel(motion,body,holder,"first opening")
    check(motion._experience.route_plan_builds==0,"No BFS or global route search")
    gap_z=-130
    configure(lower,-180,gap_z-2);configure(upper,gap_z+2,180)
    await physics_frame
    motion._experience.reset_route_plan();motion._experience.active=false;motion._experience.visits.clear()
    travel(motion,body,holder,"opening moved")
    check(motion._experience.route_plan_builds==0,"Changed opening must stay local")
    lower.queue_free();upper.queue_free();await physics_frame
    var river_motion = load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    river_motion._experience=load("res://nov_navigation_experience.gd").new("")
    river_motion._experience.working_memory.storage=""
    river_motion._experience.trial_error_enabled=true
    river_motion._episodes.storage=""
    var river_body: CharacterBody3D=river_motion.create_body(holder,null)
    var current := Vector3(18,0,-80)
    var destination := Vector3(52,0,-80)
    var crossed_bridge := false
    var river_collisions := 0
    for i in range(2000):
        var result: Dictionary=river_motion.advance(current,Vector2.ZERO,destination,0.1,river_body,holder.get_world_3d().direct_space_state,true,4)
        current=result.get("position",current)
        river_collisions+=int(result.get("collisions",0))
        check(river_motion._traversability.surface(current).walkable,"No step may enter forbidden river water")
        if current.x>=22 and current.x<=42:
            crossed_bridge=true
            check(absf(current.z+32)<=3.1,"River crossing must use physically walkable observed bridge")
        if result.get("reached",false):break
    check(current.distance_to(destination)<0.1 and crossed_bridge and river_collisions==0,"Local trial/error must discover usable river crossing without global planning")
    check(river_motion._experience.route_plan_builds==0,"River fixture cannot use BFS")
    print("Contour river final=",current," crossed_bridge=",crossed_bridge," collisions=",river_collisions)
    holder.queue_free();await process_frame
    print("Contour trial smoke: ",failures," failures")
    quit(1 if failures else 0)
