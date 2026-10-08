extends RefCounted
# Experimental bounded situation/action/outcome adapter. No position keys.
const LIMIT := 512
const SAMPLE_LIMIT := 32
const MIN_SAMPLES := 2
const LOCAL_COST_SCALE_M := 3.0
var enabled := false
var cost_shift_enabled := false
var records: Array[Dictionary] = []
var _identities: Dictionary = {}
func context(current: Vector2, goal: Vector2, rows: Array[Dictionary]) -> String:
    if not current.is_finite() or not goal.is_finite() or current.distance_to(goal)<0.1:return ""
    var normal := (goal-current).normalized()
    var observed := 0
    var clear := 0
    for row in rows:
        if row.get("source","")!="perception":continue
        var point: Vector2=row.get("point",current)
        if not point.is_finite() or point.distance_to(current)<0.05:continue
        var direction := (point-current).normalized()
        var sector := posmod(roundi(normal.angle_to(direction)/(TAU/8.0)),8)
        observed |= 1<<sector
        if bool(row.get("clear_ahead",false)):clear |= 1<<sector
    # Exact relative sensor signature: deliberately no semantic similarity claim.
    return "local-clear-v1:%d:%d" % [observed,clear]
func observe_attempt(row: Dictionary) -> bool:
    # Predictions, censored attempts, sensed-only rejections and duplicates
    # cannot become outcome evidence. Physical callers own measurement validation.
    var key := str(row.get("context",""))
    var identity := str(row.get("attempt_id",""))
    var side := int(row.get("side",0))
    var outcome := str(row.get("outcome",""))
    var distance := float(row.get("distance_m",-1))
    var initial := float(row.get("initial_remaining_m",-1))
    if key.is_empty() or identity.is_empty() or not side in [-1,1]:return false
    if not bool(row.get("physical_attempt",false)) or bool(row.get("contains_prediction",true)):return false
    if not outcome in ["arrived","contour_completed","blocked","stuck_recovery","interrupted"]:return false
    if not is_finite(distance) or distance<0 or not is_finite(initial) or initial<=0:return false
    if outcome=="interrupted":return false # No failure attribution for shutdown/goal changes.
    if _identities.has(identity):return false
    var stored := row.duplicate(true)
    # Local exits compare executed travel on a fixed sensor-scale denominator.
    # Goal distance remains telemetry and cannot make the same detour cheaper.
    var local_cost: bool=str(row.get("profile","")).ends_with("-localexit-v3")
    stored["cost_ratio"]=distance/LOCAL_COST_SCALE_M if local_cost else distance/initial
    _identities[identity]=true
    records.append(stored)
    while records.size()>LIMIT:
        _identities.erase(str(records[0].attempt_id));records.pop_front()
    return true
func recommend(key: String) -> Dictionary:
    return evaluate(key).recommendation
func _evaluate_rows(key: String, source_rows: Array[Dictionary]) -> Dictionary:
    var evaluation: Dictionary={"context":key,"reason":"disabled","alternatives":{},"recommendation":{}}
    if not enabled:return evaluation
    var sides: Dictionary={}
    for side in [-1,1]:
        var recent: Array[Dictionary]=[]
        for row in source_rows:
            if row.context==key and int(row.side)==side:recent.append(row)
        while recent.size()>SAMPLE_LIMIT:recent.pop_front()
        if recent.is_empty():
            sides[side]={"samples":0,"errors":0,"observation_ids":[]}
            continue
        var cost := 0.0
        var errors := 0
        var ids: Array=[]
        for row in recent:
            # Errors add a bounded policy penalty; an arrival with a long detour
            # retains its measured cost. Contradictions remain as separate samples.
            cost+=minf(float(row.cost_ratio),100.0)
            if not row.outcome in ["arrived","contour_completed"]:errors+=1
            var id := str(row.get("observation_id",""))
            if not id.is_empty() and not ids.has(id):ids.append(id)
        var score := cost/recent.size()+20.0*float(errors)/recent.size()
        sides[side]={"score":score,"samples":recent.size(),"errors":errors,"observation_ids":ids}
    evaluation.alternatives=sides
    if int(sides[-1].samples)<MIN_SAMPLES or int(sides[1].samples)<MIN_SAMPLES:
        evaluation.reason="insufficient_samples";return evaluation
    if int(sides[-1].errors)==int(sides[-1].samples) or int(sides[1].errors)==int(sides[1].samples):
        evaluation.reason="side_without_success";return evaluation
    var best := -1 if float(sides[-1].score)<float(sides[1].score) else 1
    var other := -best
    # Abstain on weak/equal evidence; no permanent ban or fabricated certainty.
    evaluation.score_gap=float(sides[other].score)-float(sides[best].score)
    evaluation.required_gap=0.2*maxf(1.0,float(sides[other].score))
    if float(evaluation.score_gap)<float(evaluation.required_gap):
        evaluation.reason="insufficient_margin";return evaluation
    evaluation.reason="preferred_side"
    evaluation.recommendation={"side":best,"context":key,"alternatives":sides,
        "source":"recovered-pattern-evidence" if not sides[best].observation_ids.is_empty() else "ram-pattern-evidence",
        "observation_ids":sides[best].observation_ids.duplicate(),"contains_prediction":true}
    return evaluation

const COST_SHIFT_RISE_FACTOR=1.5
const COST_SHIFT_MIN_RISE=1.0 # Three measured metres. Not failure evidence.
func evaluate(key: String) -> Dictionary:
    var original: Dictionary=_evaluate_rows(key,records)
    if not enabled or not cost_shift_enabled:return original
    var rows: Array[Dictionary]=[]
    for row in records:
        if row.context==key and str(row.get("profile","")).ends_with("-localexit-v3"):rows.append(row)
    rows.sort_custom(func(a,b):return float(a.get("ended_at_unix",0))<float(b.get("ended_at_unix",0)))
    var baseline: Dictionary={-1:[],1:[]}
    var onset := -1
    for i in range(rows.size()):
        var row: Dictionary=rows[i]
        var side: int=int(row.side)
        if baseline[side].size()<2:
            baseline[side].append(float(row.cost_ratio))
            continue
        var mean: float=(baseline[side][0]+baseline[side][1])/2.0
        if float(row.cost_ratio)>mean*COST_SHIFT_RISE_FACTOR and float(row.cost_ratio)>mean+COST_SHIFT_MIN_RISE:
            onset=i
            baseline={-1:[],1:[]}
            baseline[side].append(float(row.cost_ratio))
    if onset<0:return original
    var fresh_rows: Array[Dictionary]=[]
    var counts: Dictionary={-1:0,1:0}
    for i in range(onset,rows.size()):
        fresh_rows.append(rows[i]);counts[int(rows[i].side)]+=1
    var evaluation: Dictionary=_evaluate_rows(key,fresh_rows)
    evaluation["cost_shift"]={"basis":"measured_cost_increase","factor":COST_SHIFT_RISE_FACTOR,
        "minimum_rise_cost_units":COST_SHIFT_MIN_RISE,"onset_attempt_id":rows[onset].attempt_id,
        "retained_raw_samples":rows.size(),"fresh_samples":fresh_rows.size()}
    if counts[-1]<2 or counts[1]<2:
        var side := -1 if counts[-1]<counts[1] else 1
        evaluation.reason="cost_shift_exploration"
        evaluation.recommendation={"side":side,"context":key,"source":"pattern-exploration",
            "observation_ids":[],"contains_prediction":true}
    return evaluation
