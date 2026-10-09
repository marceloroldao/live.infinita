extends SceneTree
var failures:=0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func policy(experimental: bool):
    var value=load(get_script().resource_path.get_base_dir()+"/godot_failure_policy_008ey.gd").new() if experimental else load("res://nov_navigation_patterns.gd").new()
    value.enabled=true;value.cost_shift_enabled=true
    return value
func _initialize() -> void:
    var root_path: String=get_script().resource_path.get_base_dir()+"/../docs/"
    var tested:=0
    for geometry in ["corner","pocket","closed"]:
        var rows=JSON.parse_string(FileAccess.get_file_as_string(root_path+"OBSTACLE_FAILURE_008EX/"+geometry+"_recovered.json"))
        check(typeof(rows)==TYPE_ARRAY and rows.size()==8,"Archived actual physical evidence required")
        var original=policy(false);var candidate=policy(true)
        var keys: Dictionary={}
        for row in rows:
            check(original.observe_attempt(row) and candidate.observe_attempt(row),"Both policies accept identical actual records")
            keys[row.context]=true
        for key in keys:
            check(original.evaluate(key)==candidate.evaluate(key),geometry+": existing decision unchanged")
            tested+=1
    var facts=JSON.parse_string(FileAccess.get_file_as_string(root_path+"ASYMMETRIC_FAILURE_008EY/recovered.json"))
    var original=policy(false);var candidate=policy(true);var single_success=policy(true)
    var successes:=0
    for row in facts:
        check(original.observe_attempt(row) and candidate.observe_attempt(row),"Actual mixed evidence accepted")
        if row.outcome=="contour_completed":
            successes+=1
            if successes>1:continue
        check(single_success.observe_attempt(row),"Unmodified subset accepted")
    var key: String=facts[0].context
    check(original.evaluate(key).recommendation.is_empty(),"Production guard abstains on mixed success/failure")
    check(candidate.evaluate(key).recommendation.get("side",0)==-1,"Candidate selects repeatedly completed side from actual evidence")
    check(single_success.evaluate(key).recommendation.is_empty(),"One successful sample cannot justify preference")
    candidate.enabled=false
    check(candidate.evaluate(key).recommendation.is_empty(),"Disabled policy abstains")
    print("008EY_FAILURE_POLICY_CONTRACT "+JSON.stringify({"failures":failures,"unchanged_real_contexts":tested,
        "one_success_abstains":true,"disabled_abstains":true,"real_mixed_evidence_produces_preference":true}))
    quit(1 if failures else 0)
