extends "res://nov_navigation_patterns.gd"
# Isolated renewable-epoch policy. Retains raw facts; compares a bounded fresh epoch.
const Base=preload("res://nov_navigation_patterns.gd")
const RISE_FACTOR=1.5
const MIN_RISE=1.0 # Cost units: 3 m, not a physical failure.
func evaluate(key: String) -> Dictionary:
    var original: Dictionary=super.evaluate(key)
    if not enabled:return original
    var rows: Array[Dictionary]=[]
    for row in records:
        if row.context==key:rows.append(row)
    rows.sort_custom(func(a,b):return float(a.ended_at_unix)<float(b.ended_at_unix))
    var baseline: Dictionary={-1:[],1:[]}
    var onset := -1
    for i in range(rows.size()):
        var row: Dictionary=rows[i]
        var side: int=int(row.side)
        if baseline[side].size()<2:
            baseline[side].append(float(row.cost_ratio))
            continue
        var mean: float=(baseline[side][0]+baseline[side][1])/2.0
        if float(row.cost_ratio)>mean*RISE_FACTOR and float(row.cost_ratio)>mean+MIN_RISE:
            onset=i
            baseline={-1:[],1:[]}
            baseline[side].append(float(row.cost_ratio))
    if onset<0:return original
    var fresh=Base.new();fresh.enabled=true
    var counts: Dictionary={-1:0,1:0}
    for i in range(onset,rows.size()):
        fresh.observe_attempt(rows[i]);counts[int(rows[i].side)]+=1
    var evaluation: Dictionary=fresh.evaluate(key)
    evaluation["cost_shift"]={"basis":"measured_cost_increase","factor":RISE_FACTOR,
        "minimum_rise_cost_units":MIN_RISE,"onset_attempt_id":rows[onset].attempt_id,
        "retained_raw_samples":rows.size(),"fresh_samples":fresh.records.size()}
    if counts[-1]<2 or counts[1]<2:
        var side := -1 if counts[-1]<counts[1] else 1
        evaluation.reason="cost_shift_exploration"
        evaluation.recommendation={"side":side,"context":key,"source":"pattern-exploration",
            "observation_ids":[],"contains_prediction":true}
    return evaluation
