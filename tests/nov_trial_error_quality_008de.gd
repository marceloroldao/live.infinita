extends "res://nov_navigation_experience.gd"
# Experimental only. Physical candidates/causal baselines copied from production;
# only RAM/recall bonuses are reduced using observed complete-episode costs.
var quality_enabled := false
var quality: Dictionary = {}
var quality_adjustments := 0

func target(current: Vector2, goal: Vector2, probe: Callable = Callable(), _route_probe: Callable = Callable()) -> Vector2:
    return super.target(current,goal,probe,Callable())

func reset_trial() -> void:
    reset_route_plan()
    active = false
    visits.clear()
    trace.clear()
    failures.clear()
    routes.clear()
    recovery = false
    attempts = 0
    last_goal = Vector2.INF

func quality_key(address: String, point: Vector2) -> String:
    return "%s@%d,%d" % [address,roundi(point.x*20.0),roundi(point.y*20.0)]

func quality_bonus(address: String, point: Vector2, original_bonus: float) -> float:
    if not quality_enabled:
        return original_bonus
    var item: Dictionary = quality.get(quality_key(address,point),{})
    if not valid_quality(item):
        return original_bonus
    var penalty := maxf(0.0,float(item["remaining_cost_m"])-float(item["reference_cost_m"]))
    var adjusted := maxf(0.0,original_bonus-penalty)
    if adjusted<original_bonus:quality_adjustments += 1
    return adjusted

func valid_quality(item: Dictionary) -> bool:
    if not typeof(item.get("samples")) in [TYPE_INT,TYPE_FLOAT]:
        return false
    var count := float(item["samples"])
    if not is_finite(count) or count<1.0 or count!=floor(count):
        return false
    for field in ["remaining_cost_m","reference_cost_m"]:
        if not typeof(item.get(field)) in [TYPE_FLOAT,TYPE_INT]:
            return false
        if not is_finite(float(item[field])) or float(item[field])<0.0:
            return false
    return float(item["reference_cost_m"])<=float(item["remaining_cost_m"])

func apply_recall(value: Dictionary) -> void:
    super.apply_recall(value)
    quality.clear()
    for row in value.get("entries",[]):
        if row.get("kind","")!="successful_route_step" or not row.has("route_quality"):
            continue
        var point := Vector2(float(row["to"][0]),float(row["to"][1]))
        var address := str(row["key"])
        if recalled_routes.has(address) and recalled_routes[address]["next"].distance_to(point)<=0.05 and typeof(row["route_quality"])==TYPE_DICTIONARY and valid_quality(row["route_quality"]):
            quality[quality_key(address,point)] = row["route_quality"].duplicate(true)

func _anticipated_target(current: Vector2, goal: Vector2, probe: Callable, route_probe: Callable = Callable()) -> Vector2:
    var direct := current.move_toward(goal, CELL_M)
    var address := key(goal) + "|" + key(current)
    var temporary: Dictionary = working_memory.lookup(address)
    # A nearby goal with a fully observed clear corridor needs no remembered detour.
    # The physics probe checks the entire segment, not just its endpoint.
    if current.distance_to(goal) <= 3.0:
        var corridor: Dictionary = probe.call(goal)
        if bool(corridor.get("allowed", false)) and bool(corridor.get("clear_ahead", false)):
            _observed_route.clear()
            _route_search.cancel()
            pending = direct
            last_decision_source = "perception"
            last_observation_id = ""
            if not temporary.is_empty():
                var remembered := Vector2(float(temporary["to"][0]), float(temporary["to"][1]))
                if remembered.distance_to(direct) <= 0.05:
                    last_decision_source = "perception-working-memory-agreement"
            if last_decision_source == "perception" and memoria_enabled and recalled_routes.has(address):
                if recalled_routes[address]["next"].distance_to(direct) <= 0.05:
                    last_decision_source = "perception-memory-agreement"
            decision_evidence = {"lookahead_m": 3.0, "goal_corridor_clear": true,
                "without_memoria": [direct.x, direct.y],
                "candidates": [{"point": [direct.x, direct.y], "allowed": true,
                    "clear_ahead": true, "reason": ""}]}
            active = true
            return pending
    while not _observed_route.is_empty() and current.distance_to(_observed_route[0])<0.05:
        _observed_route.pop_front()
    if _observed_route.is_empty() and route_probe.is_valid():
        var front: Dictionary = probe.call(direct)
        var retry := current.distance_to(_route_search_origin)>=12.0 or Time.get_ticks_msec()-_route_search_at>=5000
        if _route_search.running or (retry and (not bool(front.get("clear_ahead", false)) or _exploration_heading.length_squared()>0.1)):
            if not _route_search.running:
                _route_search_origin = current
                _route_search_at = Time.get_ticks_msec()
                route_plan_builds += 1
            _observed_route = _route_search.advance(current, goal, route_probe, explored_cells, _exploration_heading, _exploration_returning)
            if _route_search.running:
                pending = current
                active = false
                last_decision_source = "perception-no-passage"
                last_observation_id = ""
                decision_evidence = {"lookahead_m": 3.0,
                    "candidates": [{"point": [current.x,current.y], "allowed": true,
                        "clear_ahead": false, "reason": "route_search_in_progress"}]}
                return current
            if _route_search.mode.begins_with("frontier") and not _observed_route.is_empty():
                _exploration_heading = (_observed_route[-1]-current).normalized()
                _exploration_returning = _route_search.mode=="frontier-return"
            print("NOV_OBSERVED_ROUTE mode=%s nodes=%d probes=%d elapsed_ms=%d max_slice_ms=%d" % [_route_search.mode, _observed_route.size(), _route_search.sampled_edges, _route_search.elapsed_ms, _route_search.max_slice_ms])
    if not _observed_route.is_empty():
        var shortcut_index := _observed_shortcut_index(current, route_probe)
        var next := current.move_toward(_observed_route[shortcut_index], CELL_M)
        var sensed: Dictionary = probe.call(next)
        if bool(sensed.get("allowed", false)):
            for i in range(shortcut_index):
                _observed_route.pop_front()
            pending = next
            active = true
            last_decision_source = "perception"
            last_observation_id = ""
            decision_evidence = {"lookahead_m": 3.0, "observed_route_range_m": 32.0, "observed_route_mode": _route_search.mode,
                "observed_route_shortcut_waypoints": shortcut_index,
                "without_memoria": [next.x,next.y],
                "candidates": [{"point": [next.x,next.y], "allowed": true,
                    "clear_ahead": bool(sensed.get("clear_ahead", false)),
                    "reason": str(sensed.get("reason", ""))}]}
            if pending.distance_to(direct)>0.05:
                anticipated_avoidances += 1
            return pending
        _invalidate_changed_route(current,next,"planned_passage_changed")
        pending = current
        active = false
        last_decision_source = "perception-no-passage"
        last_observation_id = ""
        decision_evidence = {"lookahead_m":3.0,
            "candidates":[{"point":[next.x,next.y],"allowed":false,
                "clear_ahead":false,"reason":str(sensed.get("reason","changed_passage"))}]}
        return current
    var candidates: Array[Dictionary] = [{"point": direct, "bonus": 0.0, "source": "perception", "id": ""}]
    if not temporary.is_empty():
        var next := Vector2(float(temporary["to"][0]), float(temporary["to"][1]))
        if current.distance_to(next) > 0.05 and current.distance_to(next) < 2.0:
            candidates.append({"point": next, "bonus": quality_bonus(address,next,1.5), "source": "working-memory", "id": ""})
    var local = routes.get(address)
    if local is Vector2 and current.distance_to(local) > 0.05 and current.distance_to(local) < 2.0:
        candidates.append({"point": local, "bonus": 1.5, "source": "local-experience", "id": ""})
    if memoria_enabled and recalled_routes.has(address):
        var recalled: Dictionary = recalled_routes[address]
        var next: Vector2 = recalled["next"]
        if current.distance_to(next) > 0.05 and current.distance_to(next) < 2.0:
            candidates.append({"point": next, "bonus": quality_bonus(address,next,2.0), "source": "memoria.ia", "id": recalled["id"]})
    for i in range(8):
        var direction := Vector2.RIGHT.rotated(TAU * float(i) / 8.0 + deg_to_rad(float(_probe_phase)))
        candidates.append({"point": current + direction * CELL_M, "bonus": 0.0, "source": "perception", "id": ""})
    var viable: Array[Dictionary] = []
    var clear_available := false
    var direct_clear := true
    for i in range(candidates.size()):
        var candidate: Dictionary = candidates[i]
        var point: Vector2 = candidate["point"]
        var sensed: Dictionary = probe.call(point)
        candidate["allowed"] = bool(sensed.get("allowed", false))
        candidate["reason"] = str(sensed.get("reason", ""))
        candidate["clear_ahead"] = bool(sensed.get("clear_ahead", false))
        if i == 0:
            direct_clear = bool(sensed.get("clear_ahead", false))
        if not bool(sensed.get("allowed", false)):
            if str(candidate["source"])=="working-memory":
                working_memory.invalidate_candidate(address)
            continue
        candidate["clear_ahead"] = bool(sensed.get("clear_ahead", false))
        clear_available = clear_available or candidate["clear_ahead"]
        viable.append(candidate)
    var best := INF
    var baseline_best := INF
    var baseline: Dictionary = {}
    var baseline_clear := false
    for candidate in viable:
        if str(candidate["source"]) != "memoria.ia":
            baseline_clear = baseline_clear or bool(candidate["clear_ahead"])
    var chosen: Dictionary = {}
    for candidate in viable:
        if clear_available and not bool(candidate["clear_ahead"]):
            continue
        var point: Vector2 = candidate["point"]
        var passage := edge(current, point)
        var score := point.distance_to(goal) + float(visits.get(key(point), 0)) * 4.0
        score += float(failures.get(passage, 0)) * 12.0
        if memoria_enabled and recalled_failures.has(passage):
            score += float(recalled_failures[passage]["count"]) * 12.0
        score -= float(candidate["bonus"])
        if score < best:
            best = score
            chosen = candidate
    for candidate in viable:
        if str(candidate["source"]) == "memoria.ia" or (baseline_clear and not bool(candidate["clear_ahead"])):
            continue
        var point: Vector2 = candidate["point"]
        var score := point.distance_to(goal) + float(visits.get(key(point), 0)) * 4.0
        score += float(failures.get(edge(current, point), 0)) * 12.0
        score -= float(candidate["bonus"])
        if score < baseline_best:
            baseline_best = score
            baseline = candidate
    var without_working: Dictionary = {}
    var working_baseline_clear := false
    var working_baseline_score := INF
    for candidate in viable:
        if str(candidate["source"]) != "working-memory":
            working_baseline_clear = working_baseline_clear or bool(candidate["clear_ahead"])
    for candidate in viable:
        if str(candidate["source"]) == "working-memory" or (working_baseline_clear and not bool(candidate["clear_ahead"])):
            continue
        var point: Vector2 = candidate["point"]
        var score := point.distance_to(goal) + float(visits.get(key(point), 0)) * 4.0
        score += float(failures.get(edge(current, point), 0)) * 12.0
        if memoria_enabled and recalled_failures.has(edge(current, point)):
            score += float(recalled_failures[edge(current, point)]["count"]) * 12.0
        score -= float(candidate["bonus"])
        if score < working_baseline_score:
            working_baseline_score = score
            without_working = candidate
    var sensed_rows: Array = []
    for candidate in candidates:
        var point: Vector2 = candidate["point"]
        sensed_rows.append({"point": [point.x, point.y], "allowed": candidate.get("allowed", false), "clear_ahead": candidate.get("clear_ahead", false), "reason": candidate.get("reason", ""),"memory_bonus":candidate["bonus"]})
    decision_evidence = {"lookahead_m": 3.0, "candidates": sensed_rows}
    if not baseline.is_empty():
        var base_point: Vector2 = baseline["point"]
        decision_evidence["without_memoria"] = [base_point.x, base_point.y]
    if chosen.is_empty():
        # Continue sensing other headings; no speculative failure becomes experience.
        _probe_phase = (_probe_phase + 11) % 45
        recovery = true
        active = false
        last_decision_source = "perception-no-passage"
        last_observation_id = ""
        pending = current
        return current
    pending = chosen["point"]
    decision_evidence["selected_memory_bonus"] = chosen["bonus"]
    decision_evidence["route_quality_enabled"] = quality_enabled
    if str(chosen["source"]) == "working-memory":
        working_memory_key = address
        working_memory_changed_choice = without_working.is_empty() or pending.distance_to(without_working["point"]) > 0.05
        if not without_working.is_empty():
            var baseline_point: Vector2 = without_working["point"]
            decision_evidence["without_working_memory"] = [baseline_point.x, baseline_point.y]
    last_decision_source = str(chosen["source"])
    last_observation_id = str(chosen["id"])
    var differs_from_baseline := baseline.is_empty() or pending.distance_to(baseline["point"]) > 0.05
    if memoria_enabled and differs_from_baseline:
        if last_decision_source != "memoria.ia" and not baseline.is_empty():
            var baseline_passage := edge(current, baseline["point"])
            if recalled_failures.has(baseline_passage):
                last_decision_source = "memoria.ia"
                last_observation_id = str(recalled_failures[baseline_passage]["id"])
        if last_decision_source == "memoria.ia":
            memory_decisions += 1
    elif last_decision_source == "memoria.ia":
        last_decision_source = "perception-memory-agreement"
        last_observation_id = ""
    if last_decision_source == "working-memory" and not working_memory_changed_choice:
        last_decision_source = "perception-working-memory-agreement"
    if not direct_clear and pending.distance_to(direct) > 0.05:
        anticipated_avoidances += 1
    active = true
    return pending

