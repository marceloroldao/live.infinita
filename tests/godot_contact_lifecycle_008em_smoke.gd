extends "godot_local_contour_008ei_smoke.gd"
func _initialize() -> void:
    var collector=fresh()
    collector.observe_action(action(collector,1))
    var next: Dictionary=action(collector,2)
    next.perception.contour.reset_event={"contact_serial":1,"reason":"observed_side_end"}
    collector.observe_action(next)
    check(collector.exclusions.get("observed_side_end",0)==1,"Observed side-end reset gets explicit censored reason")
    check(collector.pending.size()==1,"Only the new contact remains pending")
    collector.observe_action(action(collector,1))
    check(collector.pending.size()==1 and collector.exclusions.size()==1,"Retired contact cannot reopen or exclude its successor")
    var delayed: Dictionary=action(collector,1);delayed.outcome="blocked";delayed.collisions=1
    collector.observe_action(delayed)
    check(collector.local_rows.is_empty(),"Delayed physical failure cannot penalize another contact")
    var unknown: Dictionary=action(collector,99);unknown.perception.contour.active=false;unknown.outcome="blocked";unknown.collisions=1
    collector.observe_action(unknown)
    check(collector.local_rows.is_empty(),"Unmatched inactive frame cannot penalize current pending contact")
    var actual: Dictionary=action(collector,2);actual.outcome="blocked";actual.collisions=1
    collector.observe_action(actual)
    check(collector.local_rows.size()==1 and collector.local_rows[0].outcome=="blocked","Matching executed collision still records one real failure")
    collector.observe_action(actual)
    check(collector.local_rows.size()==1,"Matching repeated terminal callback cannot duplicate credit")
    collector=fresh()
    for serial in range(1,72):
        collector.observe_action(action(collector,serial));collector.finish_attempt(terminal("goal_changed"))
    check(collector.closed_contacts.size()==64,"Retirement index remains bounded")
    collector.observe_action(action(collector,1))
    check(collector.pending.is_empty(),"Monotonic serial protects old contacts even after bounded index eviction")
    var policy=load("res://nov_navigation_contour.gd").new()
    var rows: Array[Dictionary]=[{"point":Vector2(0,1),"source":"perception","clear_ahead":true}]
    policy.filter(Vector2.ZERO,Vector2(10,0),rows,false)
    var serial: int=policy.starts
    rows=[{"point":Vector2(0,-1),"source":"perception","clear_ahead":true}]
    policy.filter(Vector2.ZERO,Vector2(10,0),rows,false)
    check(policy.evidence().turn_pending,"Forced turn exposed before selection")
    policy.committed(Vector2.ZERO,Vector2(0,-1))
    check(policy.reset_event.get("reason")=="observed_side_end" and policy.reset_event.contact_serial==serial,"Reset carries the exact retired contact identity")
    check(policy.exit_proposal.is_empty(),"Side-end reset is not fabricated successful exit")
    print("Contact lifecycle smoke: ",failures," failures")
    quit(1 if failures else 0)
