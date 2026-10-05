extends SceneTree
class ObservedJourney:
    extends "res://nov_navigation_journey.gd"
    var beats := 0
    func save_status(force: bool = false) -> void:
        beats += 1
        super.save_status(force)
var failures := 0
var lake_active := false
var last_report: Dictionary = {}
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func water(x: float,z: float) -> Dictionary:
    var depth := 5.0-Vector2(x+100,z).length()
    if lake_active and depth>0.0:
        return {"walkable":false,"surface":"water","reason":"cognitive_lake","escape_depth_m":depth}
    return {"walkable":true,"surface":"terrain","reason":""}
func run() -> void:
    var terrain_host := Node3D.new()
    root.add_child(terrain_host)
    var terrain = load("res://world_map_cognitive_terrain.gd").new(terrain_host)
    terrain._anchors = [{"lake":true,"bias":-7.0,"radius":10.0,"position":Vector2(-100,0)}]
    check(float(terrain.surface_at(-100,0).get("escape_depth_m",0))>float(terrain.surface_at(-99,0).get("escape_depth_m",0)),"Physical lake probes must describe decreasing distance to shore")
    var holder := Node3D.new()
    root.add_child(holder)
    var wall := StaticBody3D.new()
    wall.position = Vector3(-97.5,1,0)
    var shape := BoxShape3D.new()
    shape.size = Vector3(0.3,2,1.5)
    var collision := CollisionShape3D.new()
    collision.shape = shape
    wall.add_child(collision)
    holder.add_child(wall)
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0,512.0,Callable(self,"water"))
    motion._experience.storage = ""
    motion._experience.working_memory.storage = ""
    motion._experience.trial_error_enabled = true
    motion._episodes.storage = ""
    motion._episodes.set_context({"world_id":"water-fixture","observer_entity_id":"nov"})
    motion._episodes.enabled = true
    motion._experience.working_memory.world_id = "water-fixture"
    motion._experience.working_memory.enabled = true
    motion.route_goal_id = "water-change"
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var position := Vector3(-100,0,0)
    var goal := Vector3(-92,0,0)
    var before: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
    position = before.position
    check(position.x>-100,"There must be a real unfinished movement before the lake appears")
    lake_active = true
    var traversability = motion._traversability
    var outward: Dictionary = traversability.validate_step(Vector3(-99,0,0),Vector3(-98,0,0))
    check(outward.allowed and outward.environment_escape,"An already submerged body may take an outward step")
    check(not traversability.validate_step(Vector3(-99,0,0),Vector3(-100,0,0)).allowed,"Going deeper into the lake remains blocked")
    check(not traversability.validate_step(Vector3(-94.9,0,0),Vector3(-95.1,0,0)).allowed,"A dry body cannot enter the lake")
    check(not traversability.validate_step(Vector3(21,0,0),Vector3(23,0,0)).allowed,"Static river crossing remains blocked")
    check(not traversability.validate_step(Vector3(-98.5,0,0),Vector3(-96.5,0,0),holder.get_world_3d().direct_space_state).allowed,"A lake escape cannot cross a real tree or wall")
    var raised = load("res://world_map_traversability.gd").new(func(x,_z):return 3.0 if x>-98.5 else 0.0,512.0,Callable(self,"water"))
    check(not raised.validate_step(Vector3(-99,0,0),Vector3(-98,0,0)).allowed,"Lake escape cannot bypass the maximum physical step height")
    var count := 0
    var distance := 0.0
    var reached := false
    for tick in range(1000):
        var old := position
        var old_depth := float(water(position.x,position.z).get("escape_depth_m",0))
        var result: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
        position = result.get("position",position)
        distance += position.distance_to(old)
        count += int(result.get("collisions",0))
        var next_depth := float(water(position.x,position.z).get("escape_depth_m",0))
        if old_depth>0.0 and position.distance_to(old)>0.001:
            check(next_depth<old_depth,"Every executed step while submerged must approach the margin")
        if result.get("reached",false):
            reached = true
            break
    check(reached and count==0,"Nov must escape the newly formed lake and reach the goal without collisions or teleport")
    check(motion._experience.route_plan_builds==0,"Escape must use local trial/error choices, without global route search")
    last_report = {"reached":reached,"collisions":count,"distance_after_change_m":distance,"goal":goal,"final":position,"journey":motion._journey.status()}
    print("WATER_EGRESS_RESULT ",JSON.stringify(last_report))
    motion._traversability._dynamic_surface = func(_x,_z):return {"walkable":false,"surface":"water","reason":"cognitive_lake"}
    motion._experience.active = false
    motion.route_goal_id = "missing-physical-depth"
    motion._journey = ObservedJourney.new(motion._experience.working_memory)
    motion._episodes.action_completed.connect(Callable(motion._journey,"observe_completed"))
    var blocked: Dictionary = motion.advance(Vector3(-100,0,0),Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
    check(blocked.get("position",Vector3.INF)==Vector3(-100,0,0),"Missing physical shore information must not permit a speculative escape")
    check(motion._journey.beats>0 and motion._journey.motion_state=="no_passage","A completely rejected movement must still publish a live heartbeat")
    check(motion._journey.arrivals==0 and motion._journey.completed_steps==0 and motion._journey.blocked_attempts==0,"Sensing no passage must not invent successful steps or executed collisions")
    terrain_host.queue_free()
    holder.queue_free()
    await process_frame
    print("Water egress smoke: ",failures," failures")
    quit(1 if failures else 0)
