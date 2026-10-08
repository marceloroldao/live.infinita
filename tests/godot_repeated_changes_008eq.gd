extends "godot_cost_shift_comparison_008ep.gd"
func run() -> void:
    state_path=OS.get_environment("LIVE_INFINITA_NATIVE_PATTERN_STATE")
    check(not state_path.is_empty(),"Isolated state required")
    if state_path.is_empty():quit(1);return
    if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
    var holder=Node3D.new();root.add_child(holder)
    var experimental=OS.get_environment("LIVE_INFINITA_REPEATED_POLICY")!="baseline"
    var phases: Array=[]
    var recall_path=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")
    if not recall_path.is_empty():
        initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60);opening_z=-20
        await reset_wall(holder)
        var recall: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(recall_path))
        native_travel(holder,"cold_repeated_core",true,recall)
        await physics_frame
        print("008EH_NATIVE_PATTERN_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures,"scope":"cold_repeated_recall"}))
        holder.queue_free();await process_frame
        quit(1 if failures else 0);return
    opening_z=-130
    await reset_wall(holder)
    for i in range(4):
        native_travel(holder,"training_"+str(i))
        await physics_frame
    initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60)
    for opening in [-20,-110,0,-20]:
        opening_z=opening
        await reset_wall(holder)
        var before=FileAccess.get_file_as_string(state_path)
        var base=native_travel(holder,"phase_"+str(phases.size())+"_perception",false)
        await physics_frame
        save_text(state_path,before)
        var trials: Array=[]
        for i in range(12):
            trials.append(native_travel(holder,"phase_"+str(phases.size())+"_trial_"+str(i)))
            await physics_frame
        phases.append({"opening_z":opening,"perception":base,"trials":trials})
    save_text(OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE"),FileAccess.get_file_as_string(state_path))
    print("008EH_NATIVE_PATTERN_COMPARISON "+JSON.stringify({"runs":runs,"phases":phases,
        "experimental":experimental,"failures":failures,"production_learning_demonstrated":false,
        "scope":"isolated_repeated_geometry_changes"}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
