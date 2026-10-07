extends SceneTree
var failures:=0
class Journey:
    extends RefCounted
    var identity: String="goal"
    var distance_m:=5.0
    var pending_m:=1.0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func action(collector, serial: int=1, physical: bool=true) -> Dictionary:
    return {"route_goal_id":"goal","context_start":{"world_id":"w"},"physical_attempt":physical,
        "start":[0,0],"goal":[10,0],"perception":{"contour":{"active":true,"contact_serial":serial,
        "pattern_context":collector.PROFILE+"|w|local-clear-v1:255:254","initial_side":1,"default_side":1}}}
func terminal(reason: String="arrived") -> Dictionary:
    return {"goal_id":"goal","world_id":"w","termination":reason,"quality_eligible":true,
        "distance_m":20.0,"completed_steps":10,"blocked_attempts":0,"ended_at_unix":1000}
func fresh():
    var collector=load("res://nov_navigation_pattern_collector.gd").new(Journey.new(),"")
    collector.set_context({"world_id":"w","observer_entity_id":"nov"});collector.set_enabled(true)
    return collector
func _initialize() -> void:
    var collector=fresh()
    collector.observe_action(action(collector,1))
    collector.finish_attempt(terminal("goal_changed"))
    check(collector.local_rows.is_empty(),"Goal changes cannot become failures")
    collector=fresh()
    collector.observe_action(action(collector,1,false));collector.finish_attempt(terminal("stuck_recovery"))
    check(collector.local_rows.is_empty(),"Sensed-only rejection cannot become outcome")
    collector=fresh()
    collector.observe_action(action(collector));collector.observe_action(action(collector,2));collector.finish_attempt(terminal())
    check(collector.local_rows.is_empty(),"Multiple contours have ambiguous initial-side credit")
    collector=fresh()
    collector.observe_action(action(collector));collector.finish_attempt(terminal())
    check(collector.local_rows.size()==1 and collector.local_rows[0].distance_m==16.0,"Actual cost excludes movement preceding contact")
    collector.finish_attempt(terminal())
    check(collector.local_rows.size()==1,"Terminal feedback is once-only")
    var fact: Dictionary=collector.local_rows[0].duplicate(true)
    fact["observation_id"]="structural-event:"+"a".repeat(40)
    var data: Dictionary={"schema":"live-infinita-native-pattern-recall/v1","world_id":"w",
        "generated_at_unix":1000,"world_write_authority":false,"entries":[fact]}
    check(collector.accept_recall(data,1000),"Verified exporter envelope accepted")
    check(collector.patterns.records.size()==1 and collector.patterns.records[0].has("observation_id"),"Recovery annotates same outcome without double reinforcement")
    collector.poll(1181)
    check(collector.patterns.records.size()==1 and not collector.patterns.records[0].has("observation_id"),"Expired recall loses core attribution while local evidence remains")
    var foreign:=data.duplicate(true);foreign.world_id="other"
    check(not collector.accept_recall(foreign,1000),"Cross-world recall rejected")
    collector.set_context({"world_id":"new-world","observer_entity_id":"nov"})
    check(collector.patterns.records.is_empty(),"World scope isolates decisions")
    collector=fresh()
    collector.observe_action(action(collector));collector.finish_attempt(terminal("stuck_recovery"))
    check(collector.local_rows.size()==1 and collector.local_rows[0].outcome=="stuck_recovery","Physical stuck recovery is a negative outcome before teleport")
    collector=fresh()
    collector.observe_action(action(collector))
    var ineligible:=terminal();ineligible.quality_eligible=false
    collector.finish_attempt(ineligible)
    check(collector.local_rows.is_empty(),"Ineligible arrival not recorded as successful pattern")
    print("Pattern collector smoke: ",failures," failures")
    quit(1 if failures else 0)
