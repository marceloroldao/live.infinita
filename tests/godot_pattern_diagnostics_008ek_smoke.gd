extends SceneTree
var failures:=0
func check(ok: bool,label: String) -> void:
    if not ok:push_error(label);failures+=1
func row(id: String,side: int,cost: float,outcome: String="contour_completed") -> Dictionary:
    return {"attempt_id":id,"context":"case","side":side,"distance_m":cost,
        "initial_remaining_m":1000.0,"outcome":outcome,"profile":"capsule044-height18-lookahead3-contour64-localexit-v3",
        "physical_attempt":true,"contains_prediction":false}
func _initialize() -> void:
    var memory=load("res://nov_navigation_patterns.gd").new()
    check(memory.evaluate("case").reason=="disabled","Disabled decision explained")
    memory.enabled=true
    var missing: Dictionary=memory.evaluate("case")
    check(missing.reason=="insufficient_samples" and missing.alternatives[-1].samples==0,"Missing side exposed")
    for side in [-1,1]:
        for i in range(2):memory.observe_attempt(row(str(side)+str(i),side,3.0))
    var equal: Dictionary=memory.evaluate("case")
    check(equal.reason=="insufficient_margin" and equal.score_gap==0 and equal.required_gap>0,"Equal costs explain abstention with actual gap")
    check(equal.recommendation==memory.recommend("case"),"Explanation and recommendation share evaluator")
    var preferred=load("res://nov_navigation_patterns.gd").new();preferred.enabled=true
    for side in [-1,1]:
        for i in range(2):preferred.observe_attempt(row("better"+str(side)+str(i),side,3.0 if side==-1 else 9.0))
    var decision: Dictionary=preferred.evaluate("case")
    check(decision.reason=="preferred_side" and decision.recommendation.side==-1,"Preference explanation reports chosen side")
    check(decision.recommendation==preferred.recommend("case"),"Diagnostics leave steering output identical")
    var failed=load("res://nov_navigation_patterns.gd").new();failed.enabled=true
    for side in [-1,1]:
        for i in range(2):failed.observe_attempt(row("failure"+str(side)+str(i),side,3.0,"blocked" if side==-1 else "contour_completed"))
    check(failed.evaluate("case").reason=="side_without_success" and failed.recommend("case").is_empty(),"Existing conservative failure rule preserved and visible")
    var collector=load("res://nov_navigation_pattern_collector.gd").new(null,"")
    collector.set_context({"world_id":"w"});collector.set_enabled(true)
    var key: String=collector.PROFILE+"|w|local-clear-v1:255:254"
    var fact:=row("bootstrap",1,3.0);fact.context=key;collector.patterns.observe_attempt(fact)
    check(collector.recommend(key).get("source","")=="pattern-exploration","Bootstrap stays distinct from learned preference")
    var diagnostic: Dictionary=collector.decision_diagnostics()
    check(diagnostic.reason=="insufficient_samples","Bootstrap reason captures missing measured alternatives")
    diagnostic.reason="mutated"
    check(collector.decision_diagnostics().reason=="insufficient_samples","Diagnostic callers cannot alter stored explanation")
    var source:=OS.get_environment("LIVE_INFINITA_PATTERN_DIAGNOSTIC_SOURCE")
    if not source.is_empty():
        var data=JSON.parse_string(FileAccess.get_file_as_string(source))
        var audit=load("res://nov_navigation_patterns.gd").new();audit.enabled=true
        var keys: Dictionary={}
        for fact_row in data.rows:audit.observe_attempt(fact_row);keys[str(fact_row.context)]=true
        var evaluations: Array=[]
        for context_key in keys:evaluations.append(audit.evaluate(context_key))
        print("008EK_PATTERN_AUDIT "+JSON.stringify({"scope":"read_only_replay_of_measured_live_outcomes",
            "source_rows":data.rows.size(),"evaluations":evaluations,"production_advantage_demonstrated":false}))
    print("Pattern decision diagnostics smoke: ",failures," failures")
    quit(1 if failures else 0)
