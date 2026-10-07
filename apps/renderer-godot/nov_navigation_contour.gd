extends RefCounted
# Transient contour frame from physically checked local candidates, not map coordinates.
var pattern_memory: RefCounted = null
# Explicit experiment control, never set by production.
var exploration_side := 0
var exit_proposal: Dictionary = {}
var pattern_context := ""
var pattern_recommendation: Dictionary = {}
var pattern_evaluation: Dictionary = {}
var initial_side := 0
var default_side := 0
var active := false
var heading := Vector2.ZERO
var normal := Vector2.ZERO
var origin := Vector2.ZERO
var hit_distance := 0.0
var starts := 0
var forced_turns := 0
var _turn_pending := false
const INITIAL_EXCURSION_M := 64.0
var excursion_limit := INITIAL_EXCURSION_M
var side_switches := 0
func reset() -> void:
    exit_proposal={}
    active=false
    heading=Vector2.ZERO
    normal=Vector2.ZERO
    _turn_pending=false
    excursion_limit=INITIAL_EXCURSION_M
    pattern_context="";pattern_recommendation={};pattern_evaluation={};initial_side=0;default_side=0
func filter(current: Vector2, goal: Vector2, rows: Array[Dictionary], direct_clear: bool) -> Array[Dictionary]:
    exit_proposal={}
    # A clear ray after retreat alone is insufficient: it can immediately lead
    # back to the same wall. Release after actual forward progress or a shorter
    # distance than at contact, with the direct corridor checked again.
    if active and direct_clear and (current.distance_to(goal)<hit_distance-0.75 or (current-origin).dot(normal)>=3.0):
        var proposal: Dictionary={"contact_serial":starts,"start":[current.x,current.y],"normal":[normal.x,normal.y]}
        reset()
        exit_proposal=proposal
        return rows
    if not active and direct_clear:return rows
    var clear: Array[Dictionary] = []
    for row in rows:
        if bool(row.get("clear_ahead",false)):clear.append(row)
    if clear.is_empty():return rows
    if not active:
        var chosen: Dictionary = {}
        var best := INF
        for row in clear:
            if row.get("source")!="perception":continue
            var cost: float=Vector2(row.point).distance_to(goal)
            if cost<best:best=cost;chosen=row
        if chosen.is_empty():return rows
        normal=(goal-current).normalized()
        var side: Vector2=Vector2(chosen.point)-current
        heading=(side-normal*side.dot(normal)).normalized()
        if heading.length_squared()<0.5:return rows
        default_side=1 if normal.cross(heading)>0 else -1
        initial_side=default_side
        pattern_context=""
        pattern_recommendation={}
        pattern_evaluation={}
        var requested := exploration_side
        if pattern_memory!=null:
            pattern_context=pattern_memory.context(current,goal,rows)
            pattern_recommendation=pattern_memory.recommend(pattern_context)
            if pattern_memory.has_method("decision_diagnostics"):pattern_evaluation=pattern_memory.decision_diagnostics()
            if requested==0:requested=int(pattern_recommendation.get("side",0))
        if requested in [-1,1] and requested!=default_side:
            var alternative := -heading
            var available := false
            for row in clear:
                var direction: Vector2=(Vector2(row.point)-current).normalized()
                if row.get("source")=="perception" and direction.dot(alternative)>0.5 and direction.dot(normal)>=-0.25:
                    available=true
            if available:heading=alternative;initial_side=requested
        origin=current;hit_distance=current.distance_to(goal)
        excursion_limit=INITIAL_EXCURSION_M
        active=true;starts+=1
    # Expand alternating excursions from the actual contact point. Distance is
    # measured from committed physical positions; no gap coordinates are used.
    if (current-origin).dot(heading)>=excursion_limit:
        heading=-heading
        excursion_limit*=2.0
        side_switches+=1
    var forward: Array[Dictionary] = []
    for row in clear:
        var direction: Vector2=(Vector2(row.point)-current).normalized()
        if direction.dot(heading)>=-0.1 and direction.dot(normal)>=-0.25:forward.append(row)
    _turn_pending=forward.is_empty()
    if _turn_pending:
        forced_turns+=1
        return clear
    return forward
func committed(current: Vector2, point: Vector2) -> void:
    if active and _turn_pending and current.distance_to(point)>0.05:
        # The sensed end of this side permits trying another frame; never force
        # a candidate rejected by physics, and never create failure knowledge.
        reset()
func evidence() -> Dictionary:
    return {"source":"local_observed_contour","active":active,"heading":[heading.x,heading.y],
        "normal":[normal.x,normal.y],"origin":[origin.x,origin.y],
        "exit_proposal":exit_proposal.duplicate(true),"contact_serial":starts,"pattern_context":pattern_context,"pattern_recommendation":pattern_recommendation.duplicate(true),
        "initial_side":initial_side,"default_side":default_side,"pattern_evaluation":pattern_evaluation.duplicate(true),
        "initial_side_changed":initial_side!=default_side,
        "pattern_changed_initial_side":exploration_side==0 and not pattern_recommendation.is_empty() and initial_side!=default_side,
        "side_switches":side_switches,"excursion_limit":excursion_limit,
        "global_route_search":false,"durable_learning":false}
