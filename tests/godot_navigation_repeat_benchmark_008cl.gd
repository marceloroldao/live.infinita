extends SceneTree
# Isolated physics benchmark. Its fixtures never enter the production memory.
const Experience = preload("res://nov_navigation_experience.gd")
var options: Dictionary = {}
func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        var parts := str(arg).split("=", true, 1)
        if parts.size() == 2:
            options[parts[0]] = parts[1]
    call_deferred("run")
func run() -> void:
    var holder := Node3D.new()
    root.add_child(holder)
    for fixture in [
        [Vector3(-97.5,1,0),Vector3(0.2,2,5)],
        [Vector3(-100.5,1,-2.5),Vector3(6.2,2,0.2)],
        [Vector3(-100.5,1,2.5),Vector3(6.2,2,0.2)]
    ]:
        var wall := StaticBody3D.new()
        var shape := BoxShape3D.new()
        shape.size = fixture[1]
        var collision := CollisionShape3D.new()
        collision.shape = shape
        wall.position = fixture[0]
        wall.add_child(collision)
        holder.add_child(wall)
    var motion = preload("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var results: Dictionary = {}
    var recalled: Dictionary = {}
    if options.has("--recall"):
        recalled = JSON.parse_string(FileAccess.get_file_as_string(options["--recall"]))
    var route_entries: Array = []
    for mode in ["without_memory","with_memory"]:
        if mode == "with_memory" and recalled.is_empty():
            continue
        motion._experience = Experience.new("")
        motion._experience.memoria_enabled = mode == "with_memory"
        if not recalled.is_empty():
            motion._experience.apply_recall(recalled)
        var position := Vector3(-100,0,0)
        var goal := Vector3(-94,0,0)
        var distance := 0.0
        var ticks := 0
        var reached := false
        for i in range(4000):
            var previous := position
            var movement: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,10.0)
            position = movement.get("position",position)
            distance += position.distance_to(previous)
            ticks += 1
            if movement.get("reached",false):
                reached = true
                break
        results[mode] = {"reached":reached,"ticks":ticks,"simulated_seconds":float(ticks)*0.1,
            "distance_m":distance,"collisions":motion._experience.attempts,
            "decisions":motion._experience.decision_serial,
            "causal_memory_decisions":motion._experience.memory_decisions,
            "anticipated_avoidances":motion._experience.anticipated_avoidances}
        if mode == "without_memory":
            for address in motion._experience.routes:
                var parts: PackedStringArray = str(address).split("|")
                var start: PackedStringArray = parts[1].split(",")
                var end: Vector2 = motion._experience.routes[address]
                route_entries.append({"kind":"successful_route_step","key":address,
                    "goal":[-94.0,0.0],"from":[float(start[0]),float(start[1])],
                    "to":[end.x,end.y],"observed_count":1})
    var report := {"schema":"live-infinita-navigation-repeat-benchmark/v1","fixture":"physical-U",
        "world_write_authority":false,"production_memory_written":false,
        "fixed_delta_seconds":0.1,"results":results,"observed_successful_steps":route_entries}
    var file := FileAccess.open(options["--report"],FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    file.close()
    holder.queue_free()
    await process_frame
    print("NAVIGATION_REPEAT_BENCHMARK ",JSON.stringify(results))
    quit(0 if results["without_memory"]["reached"] else 1)
