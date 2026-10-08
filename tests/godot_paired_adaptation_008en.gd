extends "godot_native_patterns_008eh.gd"
func save_text(path: String,text: String) -> void:
    var file=FileAccess.open(path,FileAccess.WRITE)
    check(file!=null,"Isolated evidence writable")
    if file!=null:file.store_string(text);file.close()
func run() -> void:
    state_path=OS.get_environment("LIVE_INFINITA_NATIVE_PATTERN_STATE")
    check(not state_path.is_empty(),"Isolated state required")
    if state_path.is_empty():quit(1);return
    if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
    var holder=Node3D.new();root.add_child(holder)
    var recall_path=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")
    var phase=OS.get_environment("LIVE_INFINITA_PAIRED_PHASE")
    var recall: Dictionary={}
    if not recall_path.is_empty():recall=JSON.parse_string(FileAccess.get_file_as_string(recall_path))
    if phase=="repaired":
        initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60);opening_z=-10
        await reset_wall(holder)
        var base=native_travel(holder,"changed_perception",false)
        await physics_frame
        var repaired=native_travel(holder,"changed_repaired_core",true,recall)
        await physics_frame
        check(repaired.recommendation.get("source","")=="recovered-pattern-evidence","Repaired core must actually influence choice")
        check(repaired.side==1 and repaired.distance_m<base.distance_m+0.01,"Recovered adapted choice is no worse than perception in this fixture")
    else:
        opening_z=-130
        await reset_wall(holder)
        for i in range(4):
            native_travel(holder,"training_"+str(i))
            await physics_frame
        var trained=FileAccess.get_file_as_string(state_path)
        save_text(OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE"),trained)
        if not recall.is_empty():
            initial=Vector3(-86,0,-60);destination=Vector3(-64,0,-60);opening_z=-110
            await reset_wall(holder)
            for repeat in range(2):
                save_text(state_path,trained)
                var base=native_travel(holder,"stable_perception_"+str(repeat),false)
                await physics_frame
                save_text(state_path,trained)
                var core=native_travel(holder,"stable_core_"+str(repeat),true,recall)
                await physics_frame
                check(core.side==-1 and core.distance_m<base.distance_m,"Paired recovered choice improves this fixed fixture")
            opening_z=-10
            await reset_wall(holder)
            save_text(state_path,trained)
            var changed_base=native_travel(holder,"changed_perception",false)
            await physics_frame
            save_text(state_path,trained)
            var stale=native_travel(holder,"changed_stale_core",true,recall)
            await physics_frame
            check(stale.distance_m>changed_base.distance_m,"Aliased changed geometry exposes stale preference cost")
            save_text(state_path,trained)
            for i in range(12):
                native_travel(holder,"adaptation_"+str(i))
                await physics_frame
            var repaired_ram=native_travel(holder,"changed_repaired_ram")
            await physics_frame
            check(repaired_ram.side==1 and repaired_ram.distance_m<stale.distance_m,"Measured new trials repair the local preference")
            save_text(OS.get_environment("LIVE_INFINITA_ADAPTED_FIXTURE"),FileAccess.get_file_as_string(state_path))
    print("008EH_NATIVE_PATTERN_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures,
        "phase":phase,"production_learning_demonstrated":false,"scope":"isolated_paired_native_physics"}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
