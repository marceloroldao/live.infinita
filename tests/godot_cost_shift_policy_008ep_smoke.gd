extends SceneTree
# Synthetic policy unit cases; these rows are not production learning evidence.
const Policy=preload("godot_cost_shift_policy_008ep.gd")
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
    var policy=Policy.new();policy.enabled=true
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
    policy.enabled=false
    check(policy.evaluate("synthetic-unit").recommendation.is_empty(),"Disabled policy never explores")
    print("008EP_COST_SHIFT_UNIT "+JSON.stringify({"failures":failures,"synthetic_unit_only":true}))
    quit(1 if failures else 0)
