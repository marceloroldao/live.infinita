extends SceneTree
var failures := 0
func check(ok: bool,label: String) -> void:
    if not ok:push_error(label);failures+=1
func sample(id: String, side: int, cost: float, outcome: String="arrived") -> Dictionary:
    return {"attempt_id":id,"context":"case","side":side,"outcome":outcome,
        "distance_m":cost*10.0,"initial_remaining_m":10.0,"physical_attempt":true,"contains_prediction":false}
func rows(current: Vector2, normal: Vector2) -> Array[Dictionary]:
    var result: Array[Dictionary]=[]
    for i in range(8):
        result.append({"point":current+normal.rotated(i*TAU/8.0),"source":"perception","clear_ahead":i!=0})
    return result
func _initialize() -> void:
    var memory=load("res://nov_navigation_patterns.gd").new()
    var key: String=memory.context(Vector2.ZERO,Vector2(10,0),rows(Vector2.ZERO,Vector2.RIGHT))
    var shifted:=Vector2(83,42)
    var rotated:=Vector2.RIGHT.rotated(PI/2)
    check(key==memory.context(shifted,shifted+rotated*30,rows(shifted,rotated)),"Pattern ignores global position, goal distance and orientation")
    check(memory.recommend("case").is_empty(),"Disabled patterns do not steer")
    memory.enabled=true
    check(memory.recommend("unknown").is_empty(),"Unknown context abstains")
    for side in [-1,1]:
        for i in range(2):
            check(memory.observe_attempt(sample(str(side)+":"+str(i),side,1.0 if side==-1 else 3.0)),"Outcome accepted")
    check(int(memory.recommend("case").get("side",0))==-1,"Measured lower-cost action preferred")
    check(not memory.observe_attempt(sample("-1:0",-1,1)),"Duplicate not reinforcing")
    check(not memory.observe_attempt(sample("censored",-1,0,"interrupted")),"Interrupted attempt has no invented failure")
    var prediction:=sample("prediction",-1,1);prediction.contains_prediction=true
    check(not memory.observe_attempt(prediction),"Prediction not ingested as outcome")
    var sensed:=sample("sensed",-1,1);sensed.physical_attempt=false
    check(not memory.observe_attempt(sensed),"Perception rejection not physical error")
    var bad:=sample("invalid",-1,1);bad.distance_m=NAN
    check(not memory.observe_attempt(bad),"Nonfinite cost rejected")
    var count: int=memory.records.size()
    for i in range(4):
        check(memory.observe_attempt(sample("physical_error_"+str(i),-1,0.2,"blocked")),"Executed blocked outcome retained")
    check(int(memory.recommend("case").get("side",0))==1,"Errors penalize context/action without deleting past successes")
    check(memory.records.size()==count+4,"Contradictions coexist with successes")
    var unsafe=load("res://nov_navigation_contour.gd").new()
    unsafe.pattern_memory=memory
    var local: Array[Dictionary]=[
        {"point":Vector2(0,1),"source":"perception","clear_ahead":true}]
    var unsafe_key: String=memory.context(Vector2.ZERO,Vector2(10,0),local)
    for side in [-1,1]:
        for i in range(2):
            var entry:=sample("unsafe"+str(side)+str(i),side,1.0 if side==-1 else 5.0)
            entry.context=unsafe_key;memory.observe_attempt(entry)
    unsafe.filter(Vector2.ZERO,Vector2(10,0),local,false)
    check(unsafe.initial_side==1,"Preferred unsafe side cannot override physically viable candidates")
    var all_fail=load("res://nov_navigation_patterns.gd").new();all_fail.enabled=true
    for side in [-1,1]:
        for i in range(2):all_fail.observe_attempt(sample("fail"+str(side)+str(i),side,1,"blocked"))
    check(all_fail.recommend("case").is_empty(),"No successful alternative means abstain")
    var bounded=load("res://nov_navigation_patterns.gd").new()
    for i in range(530):bounded.observe_attempt(sample("bound"+str(i),1,1))
    check(bounded.records.size()==512 and bounded._identities.size()==512,"Bounded evidence and duplicate index")
    print("Navigation patterns smoke: ",failures," failures")
    quit(1 if failures else 0)
