extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func _initialize() -> void:
    var frame=load("res://nov_navigation_contour.gd").new()
    frame.local_turn_continuity_enabled=true
    var rows: Array[Dictionary]=[{"point":Vector2(0,1),"source":"perception","clear_ahead":true}]
    frame.filter(Vector2.ZERO,Vector2(10,0),rows,false)
    var serial: int=frame.starts
    var context: String=frame.pattern_context
    rows=[{"point":Vector2(0,-1),"source":"perception","clear_ahead":true}]
    frame.filter(Vector2.ZERO,Vector2(10,0),rows,false)
    check(frame.evidence().turn_pending,"Sensed local end requires a direction change")
    frame.committed(Vector2.ZERO,Vector2(0,-1))
    check(frame.active and frame.starts==serial,"A local turn preserves contact identity")
    check(frame.pattern_context==context and frame.initial_side==1,"Original context and initial side preserved")
    check(frame.local_turns==1 and frame.total_local_turns==1,"One transient local turn recorded")
    check(frame.exit_proposal.is_empty() and frame.reset_event.is_empty(),"Direction change grants no success or failure")
    rows=[{"point":Vector2(-1,-2),"source":"perception","clear_ahead":true}]
    frame.filter(Vector2(0,-1),Vector2(10,0),rows,false)
    check(not frame.evidence().turn_pending,"Checked retreat can continue despite original forward normal")
    frame.reset("goal_changed")
    check(not frame.active and frame.local_turns==0 and frame.total_local_turns==1,"Context reset clears turn state, retains diagnostic count")
    frame.local_turn_continuity_enabled=false
    rows=[{"point":Vector2(0,1),"source":"perception","clear_ahead":true}]
    frame.filter(Vector2.ZERO,Vector2(10,0),rows,false)
    rows=[{"point":Vector2(0,-1),"source":"perception","clear_ahead":true}]
    frame.filter(Vector2.ZERO,Vector2(10,0),rows,false);frame.committed(Vector2.ZERO,Vector2(0,-1))
    check(not frame.active and frame.reset_event.reason=="observed_side_end","Disabled control preserves legacy reset policy")
    print("008ET contact turn contract: ",failures," failures; synthetic, never ingested")
    quit(1 if failures else 0)
