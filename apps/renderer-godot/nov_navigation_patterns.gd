extends RefCounted
# Experimental bounded situation/action/outcome adapter. No position keys.
const LIMIT := 512
const SAMPLE_LIMIT := 32
const MIN_SAMPLES := 2
var enabled := false
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
    if not outcome in ["arrived","blocked","stuck_recovery","interrupted"]:return false
    if not is_finite(distance) or distance<0 or not is_finite(initial) or initial<=0:return false
    if outcome=="interrupted":return false # No failure attribution for shutdown/goal changes.
    if _identities.has(identity):return false
    var stored := row.duplicate(true)
    stored["cost_ratio"]=distance/initial
    _identities[identity]=true
    records.append(stored)
    while records.size()>LIMIT:
        _identities.erase(str(records[0].attempt_id));records.pop_front()
    return true
func recommend(key: String) -> Dictionary:
    if not enabled:return {}
    var sides: Dictionary={}
    for side in [-1,1]:
        var recent: Array[Dictionary]=[]
        for row in records:
            if row.context==key and int(row.side)==side:recent.append(row)
        while recent.size()>SAMPLE_LIMIT:recent.pop_front()
        if recent.size()<MIN_SAMPLES:return {}
        var cost := 0.0
        var errors := 0
        var ids: Array=[]
        for row in recent:
            # Errors add a bounded policy penalty; an arrival with a long detour
            # retains its measured cost. Contradictions remain as separate samples.
            cost+=minf(float(row.cost_ratio),100.0)
            if row.outcome!="arrived":errors+=1
            var id := str(row.get("observation_id",""))
            if not id.is_empty() and not ids.has(id):ids.append(id)
        if errors==recent.size():return {}
        var score := cost/recent.size()+20.0*float(errors)/recent.size()
        sides[side]={"score":score,"samples":recent.size(),"errors":errors,"observation_ids":ids}
    var best := -1 if float(sides[-1].score)<float(sides[1].score) else 1
    var other := -best
    # Abstain on weak/equal evidence; no permanent ban or fabricated certainty.
    if float(sides[other].score)-float(sides[best].score)<0.2*maxf(1.0,float(sides[other].score)):return {}
    return {"side":best,"context":key,"alternatives":sides,
        "source":"recovered-pattern-evidence" if not sides[best].observation_ids.is_empty() else "ram-pattern-evidence",
        "observation_ids":sides[best].observation_ids.duplicate(),"contains_prediction":true}
