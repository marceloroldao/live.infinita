extends SceneTree
# Synthetic policy unit cases; these rows are not production learning evidence.
const Policy=preload("res://nov_navigation_patterns.gd")
var failures:=0
var tick:=0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func row(side: int,distance: float) -> Dictionary:
    tick+=1
    return {"context":"synthetic-unit","attempt_id":"unit-"+str(tick),"side":side,
        "outcome":"contour_completed","distance_m":distance,"initial_remaining_m":20,
        "profile":"unit-localexit-v3","physical_attempt":true,"contains_prediction":false,
        "ended_at_unix":float(tick)}
func _initialize() -> void:
    var policy=Policy.new();policy.enabled=true;policy.cost_shift_enabled=true
    for side in [1,-1,1,-1]:check(policy.observe_attempt(row(side,6 if side==1 else 3)),"Physical-shaped synthetic unit accepted")
    var original=policy.evaluate("synthetic-unit")
    check(original.reason=="preferred_side" and original.recommendation.side==-1,"Stable evidence unchanged")
    var prediction=row(-1,100);prediction.contains_prediction=true
    check(not policy.observe_attempt(prediction),"Prediction cannot trigger a shift")
    var before=JSON.stringify(policy.records)
    policy.evaluate("synthetic-unit")
    check(JSON.stringify(policy.records)==before,"Evaluation retains all facts")
    check(policy.observe_attempt(row(-1,12)),"Cost rise accepted")
    var shifted=policy.evaluate("synthetic-unit")
    check(shifted.reason=="cost_shift_exploration" and shifted.recommendation.side==1,"Probe opposite side after cost growth")
    check(shifted.recommendation.source=="pattern-exploration" and shifted.recommendation.observation_ids.is_empty(),"Exploration is not learned causal evidence")
    check(policy.evaluate("synthetic-unit").recommendation==shifted.recommendation,"No state credit for repeated proposals")
    policy.observe_attempt(row(1,15));policy.observe_attempt(row(1,15))
    check(policy.evaluate("synthetic-unit").recommendation.side==-1,"Balance fresh measured sides")
    policy.observe_attempt(row(-1,12))
    var final=policy.evaluate("synthetic-unit")
    check(final.reason=="preferred_side" and final.recommendation.side==-1,"Retain the side that remains better after shift")
    check(policy.records.size()==8,"Historical facts preserved")
    var previous_onset=final.cost_shift.onset_attempt_id
    policy.observe_attempt(row(-1,30))
    var again=policy.evaluate("synthetic-unit")
    check(again.reason=="cost_shift_exploration" and again.cost_shift.onset_attempt_id!=previous_onset,"A second increase renews the epoch")
    policy.observe_attempt(row(1,6));policy.observe_attempt(row(1,6))
    policy.observe_attempt(row(-1,30))
    var renewed=policy.evaluate("synthetic-unit")
    check(renewed.reason=="preferred_side" and renewed.recommendation.side==1,"New fresh outcomes change preference again")
    check(policy.records.size()==12,"Both epochs retain raw facts")
    policy.cost_shift_enabled=false
    check(not policy.evaluate("synthetic-unit").has("cost_shift"),"Switch off restores the full-history evaluator")
    policy.cost_shift_enabled=true
    policy.enabled=false
    check(policy.evaluate("synthetic-unit").recommendation.is_empty(),"Disabled policy never explores")
    var collector=load("res://nov_navigation_pattern_collector.gd").new(null, "")
    check(collector.status().cost_shift_enabled==(OS.get_environment("LIVE_INFINITA_NAVIGATION_COST_SHIFT")=="1"),"Collector reports configured policy flag")
    print("008ER_COST_SHIFT_UNIT "+JSON.stringify({"failures":failures,"synthetic_unit_only":true}))
    quit(1 if failures else 0)
