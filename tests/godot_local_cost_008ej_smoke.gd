extends SceneTree
var failures:=0
const PROFILE="capsule044-height18-lookahead3-contour64-localexit-v3"
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func fact(id: String,side: int,distance: float,remaining: float,outcome: String="contour_completed") -> Dictionary:
    return {"attempt_id":id,"context":"case","side":side,"distance_m":distance,
        "initial_remaining_m":remaining,"outcome":outcome,"profile":PROFILE,
        "physical_attempt":true,"contains_prediction":false}
func populate(near_left: bool):
    var memory=load("res://nov_navigation_patterns.gd").new();memory.enabled=true
    for side in [-1,1]:
        for i in range(2):
            var remaining: float=10.0 if (side==-1)==near_left else 1000.0
            memory.observe_attempt(fact(str(side)+":"+str(i),side,3.0 if side==-1 else 6.0,remaining))
    return memory
func _initialize() -> void:
    var first=populate(true);var second=populate(false)
    var a: Dictionary=first.recommend("case");var b: Dictionary=second.recommend("case")
    check(a.get("side",0)==-1 and b.get("side",0)==-1,"Same executed costs choose same side despite opposite goal distances")
    check(a.get("alternatives",{})==b.get("alternatives",{}),"Scores independent of distant destination")
    var small=load("res://nov_navigation_patterns.gd").new();small.enabled=true
    for side in [-1,1]:
        for i in range(2):small.observe_attempt(fact("short"+str(side)+str(i),side,3.0 if side==-1 else 4.0,1000.0))
    check(small.recommend("case").get("side",0)==-1,"Meaningful short detour difference is measurable on local scale")
    for i in range(4):small.observe_attempt(fact("collision"+str(i),-1,0.2,1000.0,"blocked"))
    check(small.recommend("case").get("side",0)==1,"Executed failures still outweigh cheaper successful distances")
    var equal=load("res://nov_navigation_patterns.gd").new();equal.enabled=true
    for side in [-1,1]:
        for i in range(2):equal.observe_attempt(fact("equal"+str(side)+str(i),side,3.0,10.0 if side==-1 else 1000.0))
    check(equal.recommend("case").is_empty(),"Equal local costs abstain even with unequal final goal distances")
    var path:=OS.get_environment("LIVE_INFINITA_LOCAL_COST_AUDIT_SOURCE")
    if not path.is_empty():
        var snapshot=JSON.parse_string(FileAccess.get_file_as_string(path))
        var previous=load("res://nov_navigation_patterns.gd").new();previous.enabled=true
        var revised=load("res://nov_navigation_patterns.gd").new();revised.enabled=true
        var keys: Dictionary={}
        for original in snapshot.rows:
            previous.observe_attempt(original)
            var row: Dictionary=original.duplicate(true);row.profile=PROFILE
            revised.observe_attempt(row);keys[str(row.context)]=true
        var comparisons: Array=[]
        for key in keys:
            comparisons.append({"context":key,"previous":previous.recommend(key),"local_scale":revised.recommend(key)})
        print("008EJ_LOCAL_COST_SHADOW "+JSON.stringify({"scope":"offline_replay_of_live_facts",
            "actual_live_policy_changed":false,"production_advantage_demonstrated":false,
            "source_rows":snapshot.rows.size(),"scale_m":3.0,"comparisons":comparisons}))
    print("Local cost scale smoke: ",failures," failures")
    quit(1 if failures else 0)
