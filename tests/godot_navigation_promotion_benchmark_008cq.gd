extends SceneTree
# Isolated experiment: real physical results feed the production RAM recorder.
const Experience = preload("res://nov_navigation_experience.gd")
const Recorder = preload("res://nov_navigation_episodes.gd")
const Working = preload("res://nov_navigation_working_memory.gd")
var options: Dictionary = {}
func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        var parts := str(arg).split("=",true,1)
        if parts.size()==2: options[parts[0]]=parts[1]
    call_deferred("run")
func run() -> void:
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
    var context := {"world_id":"navigation-promotion-008cq","observer_entity_id":"nov","world_sequence":1,"runtime_position":{"x":0.0,"y":0.0},"region_id":"fixture"}
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
                "promoted_entries":experience.working_memory.promoted.size()})
            if not reached: break
    var promotions := {"schema":"live-infinita-nov-navigation-promotions/v1",
        "world_id":context["world_id"],"source":"native_renderer_working_memory",
        "world_write_authority":false,"entries":ram.working_memory.promoted.values()}
    var promotion_evidence: Dictionary = {}
    for row in promotions["entries"]:
        for identity in row["decision_ids"]:
            var serial: String = str(identity).split(":")[1]
            promotion_evidence[identity] = training_actions[serial]
    var report := {"promotion_evidence_actions":promotion_evidence,"fixture":"physical-U","fixed_delta_seconds":0.1,"speed_mps":4.0,"results":results,"promotions":promotions}
    var file := FileAccess.open(options["--report"],FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    file.close()
    holder.queue_free()
    await process_frame
    print("PROMOTION_BENCHMARK ",JSON.stringify(results))
    quit(0)
