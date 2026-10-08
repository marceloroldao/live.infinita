extends "godot_local_contour_008ei_smoke.gd"
func _initialize() -> void:
    var collector=fresh()
    collector.observe_action(action(collector,1));collector.observe_action(action(collector,2))
    collector.observe_action(action(collector,1))
    var retained:=false
    for identity in collector.pending:retained=retained or str(identity).ends_with(":2")
    check(retained,"Delayed retired action cannot replace its newer contact")
    var old: Dictionary=action(collector,1);old.outcome="blocked";old.collisions=1
    collector.observe_action(old)
    check(collector.local_rows.is_empty(),"Retired collision cannot create new failure credit")
    print("Contact retirement regression: ",failures," failures")
    quit(1 if failures else 0)
