extends "godot_native_patterns_008eh.gd"
func run() -> void:
    state_path=OS.get_environment("LIVE_INFINITA_NATIVE_PATTERN_STATE")
    if state_path.is_empty():quit(1);return
    if FileAccess.file_exists(state_path):DirAccess.remove_absolute(state_path)
    initial=Vector3(-86,0,-80);destination=Vector3(-30,0,-80)
    var holder:=Node3D.new();root.add_child(holder)
    wall(holder,-180,-72);wall(holder,-68,180)
    wall(holder,-180,-92);holder.get_child(holder.get_child_count()-1).position.x=-50
    wall(holder,-88,180);holder.get_child(holder.get_child_count()-1).position.x=-50
    await physics_frame
    var measured: Dictionary=native_travel(holder,"two_sequential_obstacles",true,{},2)
    await physics_frame
    var snapshot=JSON.parse_string(FileAccess.get_file_as_string(state_path))
    check(snapshot.rows.size()>=2,"Independent local outcomes retained in actual native snapshot")
    var identities: Dictionary={}
    for row in snapshot.rows:
        check(row.outcome=="contour_completed" and row.completion_basis=="executed_exit",
            "Both obstacles require executed local exits before whole-goal arrival")
        check(float(row.exit_progress_m)>=0.75,"Actual forward displacement confirms exit")
        check(not identities.has(row.attempt_id),"Each contact has unique once-only credit")
        identities[row.attempt_id]=true
    print("008EI_MULTI_CONTOUR_RESULT "+JSON.stringify({"failures":failures,"journey":measured,
        "local_outcomes":snapshot.rows,"production_learning_demonstrated":false}))
    holder.queue_free();await process_frame
    quit(1 if failures else 0)
