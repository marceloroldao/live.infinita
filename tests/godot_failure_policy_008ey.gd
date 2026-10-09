extends "res://nov_navigation_patterns.gd"
# Isolated experimental policy. Repeated measured successes may beat an all-failed side.
# Neither geometry nor absolute position nor a preferred numeric side enters this rule.
var error_penalty := 20.0
func _evaluate_rows(key: String, source_rows: Array[Dictionary]) -> Dictionary:
    var result: Dictionary=super._evaluate_rows(key,source_rows)
    if result.reason!="side_without_success":return result
    var sides: Dictionary=result.alternatives.duplicate(true)
    for side in [-1,1]:
        var alternative: Dictionary=sides[side]
        # Diagnostic ablation changes only the explicit error component in this branch.
        alternative.score=float(alternative.score)+(error_penalty-20.0)*float(alternative.errors)/int(alternative.samples)
    var eligible: Array[int]=[]
    for side in [-1,1]:
        if int(sides[side].samples)-int(sides[side].errors)>=MIN_SAMPLES:eligible.append(side)
    if eligible.size()!=1:return result # All failures or fewer than two actual local successes: abstain.
    var best: int=eligible[0]
    var other: int=-best
    var gap: float=float(sides[other].score)-float(sides[best].score)
    var required: float=0.2*maxf(1.0,float(sides[other].score))
    result.alternatives=sides
    result.score_gap=gap;result.required_gap=required
    if gap<required:return result
    result.reason="preferred_successful_side_after_failures"
    result.recommendation={"side":best,"context":key,"alternatives":sides,
        "source":"recovered-pattern-evidence" if not sides[best].observation_ids.is_empty() else "ram-pattern-evidence",
        "observation_ids":sides[best].observation_ids.duplicate(),"contains_prediction":true}
    return result
