extends SceneTree
func _initialize()->void:
    var history=load("res://nov_animal_approach_history.gd").new()
    history.configure(OS.get_environment("LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE"))
    if not history.ready or history.records.size()!=1 or not history.pending.is_empty():
        push_error("Cold renderer must archive one pending attempt");quit(1);return
    var row:Dictionary=history.records[0]
    if row.result!="renderer_restart" or not row.censored or row.learning_eligible or row.distance_m!=null or row.ended_ms!=null:
        push_error("Restart cannot invent a measured outcome");quit(1);return
    print("008FK_RESTART "+JSON.stringify(row))
    quit(0)
