extends SceneTree
var failures:=0
class Journey:
    extends RefCounted
    var identity: String="goal"
    var distance_m:=5.0
    var pending_m:=1.0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func fresh():
    var collector=load("res://nov_navigation_pattern_collector.gd").new(Journey.new(),"")
    collector.set_context({"world_id":"w","observer_entity_id":"nov"});collector.set_enabled(true)
    return collector
func action(collector, serial: int=1) -> Dictionary:
    return {"route_goal_id":"goal","context_start":{"world_id":"w"},"physical_attempt":true,
        "executed_motion":true,"outcome":"step_reached","collisions":0,"ended_at_unix":1000.0,
        "start":[0,0],"end":[0,1],"goal":[10,0],"perception":{"contour":{"active":true,
        "contact_serial":serial,"pattern_context":collector.PROFILE+"|w|local-clear-v1:255:254",
        "initial_side":1,"default_side":1}}}
func exit_action(collector, serial: int=1, progress: float=1.0) -> Dictionary:
    var a:=action(collector,serial)
    a["start"]=[3,1];a["end"]=[3+progress,1]
    a.perception.contour={"active":false,"contact_serial":serial,
        "exit_proposal":{"contact_serial":serial,"start":[3,1],"normal":[1,0]}}
    return a
func terminal(reason: String="arrived") -> Dictionary:
    return {"goal_id":"goal","world_id":"w","termination":reason,"quality_eligible":true,
        "distance_m":20.0,"completed_steps":10,"blocked_attempts":0,"ended_at_unix":1001.0}
func _initialize() -> void:
    var collector=fresh()
    collector.observe_action(action(collector))
    var sensed:=exit_action(collector);sensed.executed_motion=false
    collector.observe_action(sensed)
    check(collector.local_rows.is_empty(),"Clear sensing without swept execution cannot create success")
    collector.observe_action(exit_action(collector,1,0.4))
    check(collector.local_rows.is_empty(),"Insufficient executed forward progress cannot finish contour")
    collector.journey.distance_m=12.0
    collector.observe_action(exit_action(collector,1,1.0))
    check(collector.local_rows.size()==1 and collector.local_rows[0].outcome=="contour_completed","Executed exit completes local outcome before journey end")
    check(collector.local_rows[0].distance_m==8.0,"Only measured distance after local contact is credited")
    collector.observe_action(exit_action(collector))
    collector.finish_attempt(terminal())
    check(collector.local_rows.size()==1,"Repeated release/terminal cannot duplicate local credit")
    collector.journey.distance_m=20.0
    collector.observe_action(action(collector,2))
    collector.journey.distance_m=25.0
    collector.observe_action(exit_action(collector,2))
    check(collector.local_rows.size()==2,"Two contours in the same journey retain independent outcomes")
    var retained: Dictionary=collector.local_rows[0].duplicate(true)
    retained["observation_id"]="structural-event:"+"a".repeat(40)
    var data: Dictionary={"schema":"live-infinita-native-pattern-recall/v2","world_id":"w",
        "generated_at_unix":1000,"world_write_authority":false,"entries":[retained]}
    check(collector.accept_recall(data,1000),"Scoped recovered local outcome accepted")
    check(collector.patterns.records.size()==2,"Core/local duplicate outcome merges once")
    collector.poll(1181)
    check(not collector.patterns.records[0].has("observation_id"),"Expired core attribution falls back to local fact")
    collector=fresh()
    collector.observe_action(action(collector));collector.observe_action(action(collector,2))
    check(collector.exclusions.get("new_contact_before_executed_exit",0)==1,"Unconfirmed prior contact excluded explicitly")
    collector.finish_attempt(terminal("goal_changed"))
    check(collector.local_rows.is_empty() and collector.exclusions.get("goal_changed",0)==1,"Goal change not mislabeled failure")
    collector=fresh()
    var blocked:=action(collector);blocked.outcome="blocked";blocked.collisions=1;blocked.executed_motion=false
    collector.observe_action(blocked)
    check(collector.local_rows.is_empty(),"Pre-execution physics rejection cannot create error penalty")
    blocked.executed_motion=true
    collector.observe_action(blocked)
    check(collector.local_rows.size()==1 and collector.local_rows[0].completion_basis=="physical_collision","Actual engine collision is negative local evidence")
    collector=fresh();collector.observe_action(action(collector));collector.finish_attempt(terminal("stuck_recovery"))
    check(collector.local_rows.size()==1 and collector.local_rows[0].outcome=="stuck_recovery","Rescue penalizes currently executed contour only")
    collector=fresh();collector.observe_action(action(collector))
    collector.set_context({"world_id":"other","observer_entity_id":"nov"})
    check(collector.pending.is_empty() and collector.exclusions.get("world_changed",0)==1,"World changes clear unfinished credit")
    print("Local contour credit smoke: ",failures," failures")
    quit(1 if failures else 0)
