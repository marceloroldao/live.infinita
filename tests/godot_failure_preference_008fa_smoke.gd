extends SceneTree
var failures:=0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func policy(active: bool):
    var value=load("res://nov_navigation_patterns.gd").new()
    value.enabled=true;value.cost_shift_enabled=true;value.failure_preference_enabled=active
    return value
func _initialize() -> void:
    var root_path: String=get_script().resource_path.get_base_dir()+"/../docs/"
    var tested:=0
    for geometry in ["corner","pocket","closed"]:
        var rows=JSON.parse_string(FileAccess.get_file_as_string(root_path+"OBSTACLE_FAILURE_008EX/"+geometry+"_recovered.json"))
        check(typeof(rows)==TYPE_ARRAY and rows.size()==8,"Actual archived records required")
        var original=policy(false);var integrated=policy(true)
        var keys: Dictionary={}
        for row in rows:
            check(original.observe_attempt(row) and integrated.observe_attempt(row),"Actual records accepted")
            keys[row.context]=true
        for key in keys:
            check(original.evaluate(key)==integrated.evaluate(key),geometry+": established decisions unchanged")
            tested+=1
    var facts=JSON.parse_string(FileAccess.get_file_as_string(root_path+"ASYMMETRIC_FAILURE_008EY/recovered.json"))
    var original=policy(false);var integrated=policy(true);var single_success=policy(true)
    var experimental=load(get_script().resource_path.get_base_dir()+"/godot_failure_policy_008ey.gd").new()
    experimental.enabled=true;experimental.cost_shift_enabled=true
    var successes:=0
    for row in facts:
        check(original.observe_attempt(row) and integrated.observe_attempt(row) and experimental.observe_attempt(row),"Identical actual mixed evidence")
        if row.outcome=="contour_completed":
            successes+=1
            if successes>1:continue
        check(single_success.observe_attempt(row),"Actual one-success subset")
    var key: String=facts[0].context
    check(original.evaluate(key).reason=="side_without_success" and original.evaluate(key).recommendation.is_empty(),"Flag off retains original guard")
    check(integrated.evaluate(key)==experimental.evaluate(key),"Native integration equals proven experimental policy")
    check(integrated.evaluate(key).recommendation.get("side",0)==-1,"Two successful exits preferred")
    check(single_success.evaluate(key).recommendation.is_empty(),"One success abstains")
    integrated.enabled=false
    check(integrated.evaluate(key).recommendation.is_empty(),"Disabled policy abstains")
    # Score-only contract: test insufficient margin without inventing physical evidence.
    var weak: Array[Dictionary]=[
        {"context":"weak","side":-1,"cost_ratio":99.0,"outcome":"contour_completed"},
        {"context":"weak","side":-1,"cost_ratio":99.0,"outcome":"contour_completed"},
        {"context":"weak","side":1,"cost_ratio":0.0,"outcome":"stuck_recovery"},
        {"context":"weak","side":1,"cost_ratio":0.0,"outcome":"stuck_recovery"}]
    var margin=policy(true)
    check(margin._evaluate_rows("weak",weak).recommendation.is_empty(),"Successful side cannot override insufficient cost margin")
    var collector=load("res://nov_navigation_pattern_collector.gd").new(null,"")
    check(collector.status().failure_preference_enabled==(OS.get_environment("LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE")=="1"),"Environment config visible")
    print("008FA_FAILURE_PREFERENCE "+JSON.stringify({"failures":failures,"unchanged_real_contexts":tested,"flag_off_retains_guard":true,"native_equals_experiment":true}))
    quit(1 if failures else 0)
