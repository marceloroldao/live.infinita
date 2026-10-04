extends SceneTree
# Reuse actual promoted memories while changing physical obstacles.
const Experience = preload("res://nov_navigation_experience.gd")
var options: Dictionary = {}
func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        var parts := str(arg).split("=",true,1)
        if parts.size()==2: options[parts[0]]=parts[1]
    call_deferred("run")
func add_wall(holder: Node3D, position: Vector3, size: Vector3) -> void:
    var wall := StaticBody3D.new()
    wall.position = position
    var collision := CollisionShape3D.new()
    var shape := BoxShape3D.new()
    shape.size = size
    collision.shape = shape
    wall.add_child(collision)
    holder.add_child(wall)
func run() -> void:
    var recall: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(options["--recall"]))
    var recalled_start := Vector2.ZERO
    var found := false
    for row in recall.get("entries",[]):
        if row.get("key","")=="-94,0|-100,0" and row.get("kind","")=="successful_route_step":
            recalled_start = Vector2(float(row["to"][0]),float(row["to"][1]))
            found = true
    if not found:
        push_error("No actual promoted memory at the fixture start")
        quit(1)
        return
    var results: Array = []
    for variant in ["unchanged_U","opened_U","remembered_step_blocked"]:
        var holder := Node3D.new()
        root.add_child(holder)
        if variant!="opened_U":
            add_wall(holder,Vector3(-97.5,1,0),Vector3(0.2,2,5))
        add_wall(holder,Vector3(-100.5,1,-2.5),Vector3(6.2,2,0.2))
        add_wall(holder,Vector3(-100.5,1,2.5),Vector3(6.2,2,0.2))
        if variant=="remembered_step_blocked":
            var blocked := Vector2(-100,0).move_toward(recalled_start,0.75)
            add_wall(holder,Vector3(blocked.x,1,blocked.y),Vector3(0.3,2,0.3))
        var motion = preload("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
        var body: CharacterBody3D = motion.create_body(holder,null)
        await physics_frame
        for mode in ["without_memory","with_memoria"]:
            for trial in range(2):
                motion._experience = Experience.new("")
                motion._experience.memoria_enabled = mode=="with_memoria"
                if mode=="with_memoria": motion._experience.apply_recall(recall)
                var position := Vector3(-100,0,0)
                var goal := Vector3(-94,0,0)
                var visited := {"-100,0":true}
                var returns := 0
                var rejected_remembered_candidates := 0
                var distance := 0.0
                var collisions := 0
                var away_distance := 0.0
                var ticks := 0
                var reached := false
                var serial := 0
                var first_selected: Array = []
                for tick in range(4000):
                    var previous := position
                    var movement: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
                    position = movement.get("position",position)
                    var travelled := position.distance_to(previous)
                    distance += travelled
                    if position.distance_to(goal)>previous.distance_to(goal)+0.0001:
                        away_distance += travelled
                    collisions += int(movement.get("collisions",0))
                    ticks += 1
                    if motion._experience.decision_serial!=serial:
                        serial = motion._experience.decision_serial
                        var evidence: Dictionary = motion._experience.decision_evidence
                        if first_selected.is_empty():
                            first_selected = [motion._experience.pending.x,motion._experience.pending.y]
                        if mode=="with_memoria":
                            var address: String = motion._experience.key(Vector2(goal.x,goal.z))+"|"+motion._experience.key(Vector2(previous.x,previous.z))
                            if motion._experience.recalled_routes.has(address):
                                var remembered: Vector2 = motion._experience.recalled_routes[address]["next"]
                                for candidate in evidence.get("candidates",[]):
                                    var point := Vector2(float(candidate["point"][0]),float(candidate["point"][1]))
                                    if point.distance_to(remembered)<0.001 and not candidate.get("allowed",false):
                                        rejected_remembered_candidates += 1
                                        break
                    if not motion._experience.active and travelled>0.001 and int(movement.get("collisions",0))==0 and movement.get("allowed",false):
                        var cell: String = motion._experience.key(Vector2(position.x,position.z))
                        if visited.has(cell): returns += 1
                        visited[cell] = true
                    if movement.get("reached",false):
                        reached = true
                        break
                results.append({"variant":variant,"mode":mode,"trial":trial+1,"reached":reached,
                    "distance_m":distance,"simulated_seconds":ticks*0.1,"ticks":ticks,
                    "decisions":motion._experience.decision_serial,"collisions":collisions,
                    "causal_memoria_decisions":motion._experience.memory_decisions,
                    "revisited_end_cells":returns,"distance_away_from_goal_m":away_distance,
                    "rejected_remembered_candidates":rejected_remembered_candidates,
                    "first_selected":first_selected,"remaining_goal_m":position.distance_to(goal)})
        holder.queue_free()
        await process_frame
        await physics_frame
    var report := {"schema":"live-infinita-navigation-environment-benchmark/v1",
        "scope":"isolated_physics_with_actual_promoted_recall",
        "production_memory_written":false,"world_write_authority":false,
        "remembered_start_step":[recalled_start.x,recalled_start.y],
        "results":results,"fixed_delta_seconds":0.1,"speed_mps":4.0}
    var file := FileAccess.open(options["--report"],FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    file.close()
    print("ENVIRONMENT_BENCHMARK ",JSON.stringify(results))
    quit(0)
