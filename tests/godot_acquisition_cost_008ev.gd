extends "godot_native_patterns_008eh.gd"
func run() -> void:
    state_path=OS.get_environment("LIVE_INFINITA_NATIVE_PATTERN_STATE")
    check(not state_path.is_empty(),"Isolated state required")
    if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
    var holder:=Node3D.new();root.add_child(holder)
    opening_z=-130
    await reset_wall(holder)
    var fixture:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE")
    var phase:=OS.get_environment("LIVE_INFINITA_ACQUISITION_PHASE")
    if phase=="training":
        for i in range(4):
            native_travel(holder,"training_perception_"+str(i),false)
            await physics_frame
        for i in range(4):
            native_travel(holder,"training_memory_"+str(i))
            await physics_frame
        var file:=FileAccess.open(fixture,FileAccess.WRITE)
        file.store_string(FileAccess.get_file_as_string(state_path));file.close()
    else:
        var recall=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")))
        initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60)
        for scenario in ["stable","changed"]:
            opening_z=-110 if scenario=="stable" else -10
            await reset_wall(holder)
            for i in range(10 if scenario=="stable" else 1):
                # Each pair uses the same cold snapshot. No trial can train its successor.
                if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
                native_travel(holder,scenario+"_perception_"+str(i),false)
                await physics_frame
                if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
                native_travel(holder,scenario+"_core_"+str(i),true,recall)
                await physics_frame
    print("008EH_NATIVE_PATTERN_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
