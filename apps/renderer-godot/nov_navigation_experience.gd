extends RefCounted
# Presentation navigator: local experience plus retrieved Memoria.ia evidence; no World State write authority.
const CELL_M := 1.0
const LIMIT := 4096
const SHORTCUT_RANGE_M := 6.0
const SHORTCUT_PROBES := 3
var route_shortcuts_enabled := true
var failures: Dictionary = {}
var visits: Dictionary = {}
var routes: Dictionary = {}
var trace: Array[Vector2] = []
var pending := Vector2.ZERO
var source := Vector2.ZERO
var active := false
var recovery := false
var attempts := 0
var last_goal := Vector2(INF, INF)
var storage := ""
var recalled_failures: Dictionary = {}
var recalled_routes: Dictionary = {}
var memoria_enabled := true
var memory_decisions := 0
var anticipated_avoidances := 0
var last_decision_source := "local-experience"
var last_observation_id := ""
var _probe_phase := 0
var decision_serial := 0
var decision_evidence: Dictionary = {}
var working_memory = preload("res://nov_navigation_working_memory.gd").new()
var _observed_route: Array[Vector2] = []
var _route_search = preload("res://nov_observed_route.gd").new()
var route_plan_builds := 0
var route_revision_count := 0
var _route_revision: Dictionary = {}
var explored_cells: Dictionary = {}
var _exploration_heading := Vector2.ZERO
var _exploration_returning := false
var _route_search_origin := Vector2(INF, INF)
var _route_search_at := -10000
var working_memory_key := ""
var working_memory_changed_choice := false

func _init(path: String = "user://nov-navigation-008cd.cfg") -> void:
    storage = path
    var cfg := ConfigFile.new()
    if not storage.is_empty() and cfg.load(storage) == OK:
        routes = cfg.get_value("experience", "routes", {})
        if routes.size() > LIMIT:
            routes.clear()
        failures = cfg.get_value("experience", "failures", {})
        if failures.size() > LIMIT:
            failures.clear()

func reset_route_plan() -> void:
    _route_revision.clear()
    explored_cells.clear()
    _exploration_heading = Vector2.ZERO
    _exploration_returning = false
    _observed_route.clear()
    _route_search.cancel()
    _route_search_origin = Vector2(INF,INF)

func key(p: Vector2) -> String:
    return "%d,%d" % [roundi(p.x / CELL_M), roundi(p.y / CELL_M)]

func edge(a: Vector2, b: Vector2) -> String:
    return key(a) + ">" + key(b)

func save() -> void:
    if storage.is_empty() or working_memory.enabled:
        return
    var cfg := ConfigFile.new()
    cfg.set_value("experience", "failures", failures)
    cfg.set_value("experience", "routes", routes)
    var result := cfg.save(storage)
    if result != OK:
        push_warning("NOV navigation experience could not persist: %s" % result)

func target(current: Vector2, goal: Vector2, probe: Callable = Callable(), route_probe: Callable = Callable()) -> Vector2:
    if last_goal.distance_to(goal) > 2.0:
        active = false
        visits.clear()
        trace.clear()
        _observed_route.clear()
        _route_search.cancel()
        _route_search_origin = Vector2(INF,INF)
        explored_cells.clear()
        _exploration_heading = Vector2.ZERO
        _exploration_returning = false
        _route_revision.clear()
        last_goal = goal
    explored_cells[_route_search.coverage_key(current)] = true
    while explored_cells.size()>LIMIT:
        explored_cells.erase(explored_cells.keys()[0])
    if active:
        if route_probe.is_valid() and not bool(route_probe.call(current,pending)):
            _invalidate_changed_route(current,pending,"pending_passage_changed")
        else:
            return pending
    decision_serial += 1
    decision_evidence = {}
    working_memory_key = ""
    working_memory_changed_choice = false
    source = current
    if trace.is_empty():
        trace.append(current)
    if probe.is_valid():
        var result := _anticipated_target(current, goal, probe, route_probe)
        if not _route_revision.is_empty():
            decision_evidence["route_revision"] = _route_revision.duplicate(true)
            if active:
                _route_revision.clear()
        return result
    var remembered = routes.get(key(goal) + "|" + key(current))
    if remembered is Vector2 and current.distance_to(remembered) > 0.05 and current.distance_to(remembered) < 2.0:
        pending = remembered
        active = true
        return pending
    if current.distance_to(goal) <= CELL_M and not failures.has(edge(current, goal)):
        pending = goal
        active = true
        return pending
    if failures.has(edge(current, current.move_toward(goal, CELL_M))):
        recovery = true
    if not recovery:
        pending = current.move_toward(goal, CELL_M)
    else:
        var best := INF
        for i in range(9):
            var direction := Vector2.RIGHT.rotated(TAU * float(i) / 8.0)
            var next := current + direction * CELL_M
            if i == 8:
                next = current.move_toward(goal, CELL_M)
            var score := next.distance_to(goal) + float(visits.get(key(next), 0)) * 4.0
            score += float(failures.get(edge(current, next), 0)) * 12.0
            if score < best:
                best = score
                pending = next
    active = true
    return pending

func blocked() -> void:
    if not active:
        return
    var k := edge(source, pending)
    routes.erase(key(last_goal) + "|" + key(source))
    failures[k] = mini(100, int(failures.get(k, 0)) + 1)
    if failures.size() > LIMIT:
        failures.erase(failures.keys()[0])
    visits[key(source)] = int(visits.get(key(source), 0)) + 1
    attempts += 1
    recovery = true
    active = false
    _invalidate_changed_route(source,pending,"executed_passage_blocked")
    # Save collision evidence immediately; no frame-rate writes on free movement.
    save()

func arrived(goal: Vector2) -> void:
    for i in range(trace.size()):
        if key(trace[i]) == key(pending):
            trace.resize(i)
            break
    trace.append(pending)
    if trace.size() > LIMIT:
        trace.pop_front()
    visits[key(pending)] = int(visits.get(key(pending), 0)) + 1
    if visits.size() > LIMIT:
        visits.erase(visits.keys()[0])
    active = false
    if pending.distance_to(goal) < 0.1:
        if not working_memory.enabled:
            for i in range(trace.size() - 1):
                routes[key(goal) + "|" + key(trace[i])] = trace[i + 1]
            while routes.size() > LIMIT:
                routes.erase(routes.keys()[0])
        save()
        trace.clear()
        recovery = false
        visits.clear()


func apply_recall(snapshot: Dictionary) -> void:
    recalled_failures.clear()
    recalled_routes.clear()
    # Finish the current physically checked step; new evidence affects the next decision.
    var rows = snapshot.get("entries", [])
    if typeof(rows) != TYPE_ARRAY:
        return
    for item in rows:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        var row: Dictionary = item
        var identity := str(row.get("observation_id", ""))
        if not identity.begins_with("structural-event:") or identity.length() != 57:
            continue
        var address := str(row.get("key", ""))
        var kind := str(row.get("kind", ""))
        if kind == "blocked_passage":
            recalled_failures[address] = {"count": clampi(int(row.get("observed_count", 0)), 0, 100), "id": identity}
        elif kind == "successful_route_step":
            var next = row.get("to", [])
            if typeof(next) == TYPE_ARRAY and next.size() == 2:
                var point := Vector2(float(next[0]), float(next[1]))
                if point.is_finite() and absf(point.x) <= 2048.0 and absf(point.y) <= 2048.0:
                    recalled_routes[address] = {"next": point, "id": identity}

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
            candidates.append({"point": next, "bonus": 1.5, "source": "working-memory", "id": ""})
    var local = routes.get(address)
    if local is Vector2 and current.distance_to(local) > 0.05 and current.distance_to(local) < 2.0:
        candidates.append({"point": local, "bonus": 1.5, "source": "local-experience", "id": ""})
    if memoria_enabled and recalled_routes.has(address):
        var recalled: Dictionary = recalled_routes[address]
        var next: Vector2 = recalled["next"]
        if current.distance_to(next) > 0.05 and current.distance_to(next) < 2.0:
            candidates.append({"point": next, "bonus": 2.0, "source": "memoria.ia", "id": recalled["id"]})
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
        sensed_rows.append({"point": [point.x, point.y], "allowed": candidate.get("allowed", false), "clear_ahead": candidate.get("clear_ahead", false), "reason": candidate.get("reason", "")})
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


# Shortcuts stay inside the already planned local path and use the same complete
# physics corridor probe as planning. The movement step is still sensed/executed.
func _observed_shortcut_index(current: Vector2, route_probe: Callable) -> int:
    if not route_shortcuts_enabled or not route_probe.is_valid():
        return 0
    var end_index := 0
    var length := 0.0
    var previous := current
    for i in range(mini(_observed_route.size(), SHORTCUT_PROBES + 1)):
        length += previous.distance_to(_observed_route[i])
        if length > SHORTCUT_RANGE_M:
            break
        end_index = i
        previous = _observed_route[i]
    for i in range(end_index, 0, -1):
        if bool(route_probe.call(current, _observed_route[i])):
            return i
    return 0


func _invalidate_changed_route(current: Vector2, rejected: Vector2, reason: String) -> void:
    working_memory.invalidate_candidate(key(last_goal)+"|"+key(source))
    working_memory.invalidate_candidate(key(last_goal)+"|"+key(current))
    routes.erase(key(last_goal)+"|"+key(source))
    active = false
    _observed_route.clear()
    _route_search.cancel()
    _route_search_origin = Vector2(INF,INF)
    _route_search_at = -10000
    # These are transient exploration hints, not durable knowledge.
    explored_cells.clear()
    explored_cells[_route_search.coverage_key(current)] = true
    _exploration_heading = Vector2.ZERO
    _exploration_returning = false
    route_revision_count += 1
    _route_revision = {"reason":reason,"from":[current.x,current.y],
        "rejected":[rejected.x,rejected.y],
        "detected_at_unix":Time.get_unix_time_from_system()}
