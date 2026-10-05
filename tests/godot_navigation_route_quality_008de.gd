extends SceneTree
# Isolated experiment: real physical results feed the production RAM recorder.
const Experience = preload("res://nov_trial_error_quality_008de.gd")
const Recorder = preload("res://nov_navigation_episodes.gd")
const Working = preload("res://nov_navigation_working_memory.gd")
var options: Dictionary = {}
func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        var parts := str(arg).split("=",true,1)
        if parts.size()==2: options[parts[0]]=parts[1]
    call_deferred("run")
func run() -> void:
    if options.has("--evaluate"):
        await evaluate()
        return
    var holder := Node3D.new()
    root.add_child(holder)
    for fixture in [[Vector3(-97.5,1,0),Vector3(0.2,2,5)],[Vector3(-100.5,1,-2.5),Vector3(6.2,2,0.2)],[Vector3(-100.5,1,2.5),Vector3(6.2,2,0.2)]]:
        var wall := StaticBody3D.new()
        wall.position = fixture[0]
        var collision := CollisionShape3D.new()
        var shape := BoxShape3D.new()
        shape.size = fixture[1]
        collision.shape = shape
        wall.add_child(collision)
        holder.add_child(wall)
    var motion = preload("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var context := {"world_id":"navigation-route-quality-008de","observer_entity_id":"nov","world_sequence":1,"runtime_position":{"x":0.0,"y":0.0},"region_id":"fixture"}
    var results: Array = []
    var training_actions: Dictionary = {}
    var ram = Experience.new("")
    ram.memoria_enabled = false
    ram.working_memory = Working.new("")
    ram.working_memory.world_id = context["world_id"]
    ram.working_memory.enabled = true
    var recall: Dictionary = {}
    if options.has("--recall"):
        recall = JSON.parse_string(FileAccess.get_file_as_string(options["--recall"]))
    for mode in ["without_memory","ram_training","after_restart_memoria"]:
        if mode=="after_restart_memoria" and recall.is_empty(): continue
        var count := 6 if mode=="ram_training" else 2
        for trial in range(count):
            var experience = ram if mode=="ram_training" else Experience.new("")
            if mode!="ram_training":
                experience.working_memory = Working.new("")
                experience.memoria_enabled = mode=="after_restart_memoria"
                if mode=="after_restart_memoria": experience.apply_recall(recall)
            experience.reset_trial()
            motion._experience = experience
            motion._episodes = Recorder.new("")
            motion._episodes.enabled = true
            motion._episodes.set_context(context)
            motion._episodes.action_completed.connect(Callable(experience.working_memory,"observe_completed"))
            var completed_actions: Array = []
            motion._episodes.action_completed.connect(func(action): completed_actions.append(action))
            var serial_start: int = experience.decision_serial
            var causal_start: int = experience.working_memory.causal_reuses
            var memory_start: int = experience.memory_decisions
            var position := Vector3(-100,0,0)
            var goal := Vector3(-94,0,0)
            var distance := 0.0
            var collisions := 0
            var ticks := 0
            var reached := false
            for tick in range(4000):
                var previous := position
                var movement: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
                position = movement.get("position",position)
                distance += position.distance_to(previous)
                collisions += int(movement.get("collisions",0))
                ticks += 1
                if movement.get("reached",false):
                    reached = true
                    break
            var verified_ram := 0
            var verified_memoria := 0
            var observation_ids: Array = []
            for action in completed_actions:
                if mode=="ram_training":
                    training_actions[str(action["decision_serial"])] = action
                var baseline = action.get("perception",{}).get("without_working_memory",[])
                var selected: Array = action["selected"]
                if action.get("working_memory_changed_choice",false) and baseline.size()==2:
                    if Vector2(float(selected[0]),float(selected[1])).distance_to(Vector2(float(baseline[0]),float(baseline[1])))>0.05:
                        verified_ram += 1
                var without_memoria = action.get("perception",{}).get("without_memoria",[])
                if action.get("decision_source","")=="memoria.ia" and without_memoria.size()==2:
                    if Vector2(float(selected[0]),float(selected[1])).distance_to(Vector2(float(without_memoria[0]),float(without_memoria[1])))>0.05:
                        verified_memoria += 1
                        if not observation_ids.has(action["memory_observation_id"]):
                            observation_ids.append(action["memory_observation_id"])
            results.append({"mode":mode,"trial":trial+1,"reached":reached,"ticks":ticks,"simulated_seconds":ticks*0.1,
                "distance_m":distance,"collisions":collisions,"decisions":experience.decision_serial-serial_start,
                "promotion_counted_ram_reuses":experience.working_memory.causal_reuses-causal_start,
                "verified_causal_ram_actions":verified_ram,"verified_causal_memoria_actions":verified_memoria,
                "selected_observation_ids":observation_ids,
                "causal_memoria_decisions":experience.memory_decisions-memory_start,
                "completed_actions":completed_actions.size(),"ram_entries":experience.working_memory.entries.size(),
                "actions":completed_actions.duplicate(true),"promoted_entries":experience.working_memory.promoted.size(),"route_plan_builds":experience.route_plan_builds})
            if not reached: break
    var promotions := {"schema":"live-infinita-nov-navigation-promotions/v1",
        "world_id":context["world_id"],"source":"native_renderer_working_memory",
        "world_write_authority":false,"entries":ram.working_memory.promoted.values()}
    var promotion_evidence: Dictionary = {}
    for row in promotions["entries"]:
        for identity in row["decision_ids"]:
            var serial: String = str(identity).split(":")[1]
            promotion_evidence[identity] = training_actions[serial]
    var report := {"promotion_evidence_actions":promotion_evidence,"fixture":"physical-U","fixed_delta_seconds":0.1,"speed_mps":4.0,"results":results,"promotions":promotions,"ram_snapshot":ram.working_memory.entries.duplicate(true)}
    var file := FileAccess.open(options["--report"],FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    file.close()
    holder.queue_free()
    await process_frame
    print("PROMOTION_BENCHMARK ",JSON.stringify(results))
    quit(0)

func add_box(holder: Node3D, position: Vector3, size: Vector3) -> void:
    var wall := StaticBody3D.new()
    wall.position = position
    var collision := CollisionShape3D.new()
    var shape := BoxShape3D.new()
    shape.size = size
    collision.shape = shape
    wall.add_child(collision)
    holder.add_child(wall)

func evaluate() -> void:
    var seed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(options["--seed"]))
    var recall: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(options["--recall"]))
    var results: Array = []
    var reference: Array = seed["blocked_to"]
    var reference_from: Array = seed["blocked_from"]
    var remembered := Vector2(float(reference[0]),float(reference[1]))
    for variant in ["unchanged_U","opened_U","remembered_step_blocked"]:
        var holder := Node3D.new()
        root.add_child(holder)
        if variant!="opened_U":
            add_box(holder,Vector3(-97.5,1,0),Vector3(0.2,2,5))
        add_box(holder,Vector3(-100.5,1,-2.5),Vector3(6.2,2,0.2))
        add_box(holder,Vector3(-100.5,1,2.5),Vector3(6.2,2,0.2))
        if variant=="remembered_step_blocked":
            var point := Vector2(float(reference_from[0]),float(reference_from[1])).move_toward(remembered,0.75)
            add_box(holder,Vector3(point.x,1,point.y),Vector3(0.3,2,0.3))
        var motion = preload("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
        var body: CharacterBody3D = motion.create_body(holder,null)
        await physics_frame
        for mode in ["without_memory","with_trained_ram","after_restart_memoria"]:
            for trial in range(2):
                # Every evaluation starts with identical empty planning state.
                # Only the same verified knowledge is supplied through RAM or recall.
                var experience = Experience.new("")
                experience.working_memory = Working.new("")
                experience.memoria_enabled = mode=="after_restart_memoria"
                if mode=="with_trained_ram":
                    experience.working_memory.world_id = seed["world_id"]
                    experience.working_memory.enabled = true
                    experience.working_memory.entries = seed["ram_entries"].duplicate(true)
                    for key in experience.working_memory.entries:
                        experience.working_memory.entries[key]["last_ms"] = Time.get_ticks_msec()
                if mode=="after_restart_memoria":
                    experience.apply_recall(recall)
                experience.quality_enabled = options.get("--quality","false")=="true"
                if mode=="with_trained_ram":
                    experience.quality = seed.get("quality",{}).duplicate(true)
                motion._experience = experience
                motion._episodes = Recorder.new("")
                motion._episodes.enabled = true
                motion._episodes.set_context({"world_id":seed["world_id"],"observer_entity_id":"nov",
                    "world_sequence":1,"runtime_position":{"x":0.0,"y":0.0},"region_id":"fixture"})
                var actions: Array = []
                # No observe_completed callback: knowledge is frozen in all arms.
                motion._episodes.action_completed.connect(func(a):actions.append(a.duplicate(true)))
                var position := Vector3(-100,0,0)
                var goal := Vector3(-94,0,0)
                var distance := 0.0
                var collisions := 0
                var moving_ticks := 0
                var planning_ticks := 0
                var returns := 0
                var visited := {"-100,0":true}
                var reached := false
                for tick in range(4000):
                    var previous := position
                    var result: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,holder.get_world_3d().direct_space_state,true,4.0)
                    position = result.get("position",position)
                    var travel := position.distance_to(previous)
                    distance += travel
                    collisions += int(result.get("collisions",0))
                    if travel>0.001:moving_ticks += 1
                    if experience._route_search.running:planning_ticks += 1
                    if not experience.active and travel>0.001:
                        var address: String = experience.key(Vector2(position.x,position.z))
                        if visited.has(address):returns += 1
                        visited[address] = true
                    if result.get("reached",false):
                        reached = true
                        break
                var causal_ram := 0
                var causal_memoria := 0
                var ids: Array = []
                for a in actions:
                    if not a.outcome in ["step_reached","goal_reached"]:continue
                    var selected := Vector2(float(a.selected[0]),float(a.selected[1]))
                    var baseline: Array = a.perception.get("without_working_memory",[])
                    if a.get("working_memory_changed_choice",false) and baseline.size()==2 and selected.distance_to(Vector2(float(baseline[0]),float(baseline[1])))>0.05:
                        causal_ram += 1
                    baseline = a.perception.get("without_memoria",[])
                    if a.decision_source=="memoria.ia" and baseline.size()==2 and selected.distance_to(Vector2(float(baseline[0]),float(baseline[1])))>0.05:
                        causal_memoria += 1
                        if not ids.has(a.memory_observation_id):ids.append(a.memory_observation_id)
                results.append({"variant":variant,"mode":mode,"trial":trial+1,
                    "reached":reached,"distance_m":distance,"collisions":collisions,
                    "remaining_goal_m":position.distance_to(goal),"route_plan_builds":experience.route_plan_builds,
                    "moving_seconds":moving_ticks*0.1,"planning_ticks":planning_ticks,
                    "revisited_end_cells":returns,"verified_causal_ram_actions":causal_ram,
                    "verified_causal_memoria_actions":causal_memoria,
                    "selected_observation_ids":ids,"completed_actions":actions.size(),
                    "loaded_knowledge":seed["ram_entries"].size() if mode!="without_memory" else 0,
                    "quality_enabled":experience.quality_enabled,"quality_adjustments":experience.quality_adjustments,"actions":actions})
        holder.queue_free()
        await process_frame
        await physics_frame
    var file := FileAccess.open(options["--report"],FileAccess.WRITE)
    file.store_string(JSON.stringify({"results":results}))
    file.close()
    print("CAUSALITY_EVALUATION_DONE trials=",results.size())
    quit(0)
