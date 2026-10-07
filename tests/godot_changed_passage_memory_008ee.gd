extends "godot_physical_memory_comparison_008ed.gd"
# Training is on the old gap; every comparison arm starts fresh on the changed layout.
class DiagnosticMemory:
    extends "res://nov_navigation_working_memory.gd"
    var physical_invalidations := 0
    func _init() -> void:super("")
    func invalidate_candidate(key: String) -> void:
        if entries.has(key):physical_invalidations+=1
        super.invalidate_candidate(key)

func new_memory():
    var memory=DiagnosticMemory.new()
    memory.world_id="physical-benchmark-008ed"
    return memory
func clone_training(original):
    var memory=new_memory()
    memory.enabled=true
    memory.entries=original.entries.duplicate(true)
    memory.quality=original.quality.duplicate(true)
    return memory
func changed_travel(holder: Node3D,memory,label: String,recall: Dictionary = {}) -> Dictionary:
    var count: int=memory.physical_invalidations
    var result: Dictionary=travel(holder,memory,label,recall)
    result["ram_physical_invalidations"]=memory.physical_invalidations-count
    result["learned_opening_z"]=-30.0
    return result
func run() -> void:
    var holder:=Node3D.new();root.add_child(holder)
    opening_z=-30.0
    wall(holder,-180,opening_z-2);wall(holder,opening_z+2,180)
    await physics_frame
    var training_memory=new_memory();training_memory.enabled=true
    var training: Dictionary=travel(holder,training_memory,"training")
    check(training.arrived and training_memory.entries.size()>0,"Old passage must be learned from real motion")
    await physics_frame
    for node in holder.get_children():node.queue_free()
    await physics_frame
    opening_z=-130.0
    wall(holder,-180,opening_z-2);wall(holder,opening_z+2,180)
    await physics_frame
    var baseline_memory=new_memory();baseline_memory.enabled=false
    changed_travel(holder,baseline_memory,"perception")
    await physics_frame
    var old_memory=clone_training(training_memory)
    changed_travel(holder,old_memory,"ram_stale_1")
    await physics_frame
    # Independent replay, not training on the first changed-map result.
    var old_memory_second=clone_training(training_memory)
    changed_travel(holder,old_memory_second,"ram_stale_2")
    await physics_frame
    var recall_path:=OS.get_environment("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL")
    if not recall_path.is_empty():
        var recall=JSON.parse_string(FileAccess.get_file_as_string(recall_path))
        check(typeof(recall)==TYPE_DICTIONARY and not recall.get("entries",[]).is_empty(),"Verified old-passage core record required")
        if typeof(recall)==TYPE_DICTIONARY:
            var cold_memory=new_memory();cold_memory.enabled=false
            changed_travel(holder,cold_memory,"verified_core_recall",recall)
            await physics_frame
    print("008ED_PHYSICAL_COMPARISON "+JSON.stringify({"runs":runs,"failures":failures,
        "same_start_goal_obstacles":true,"speed_mps":4,"dt_seconds":0.1,
        "training_opening_z":-30.0,"comparison_opening_z":-130.0,
        "same_changed_layout_for_all_comparison_arms":true,
        "scope":"isolated_real_capsule_changed_passage","production_learning_demonstrated":false}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
