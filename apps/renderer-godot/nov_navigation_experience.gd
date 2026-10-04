extends RefCounted
# Presentation navigator: local experience plus retrieved Memoria.ia evidence; no World State write authority.
const CELL_M := 1.0
const LIMIT := 4096
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

func key(p: Vector2) -> String:
    return "%d,%d" % [roundi(p.x / CELL_M), roundi(p.y / CELL_M)]

func edge(a: Vector2, b: Vector2) -> String:
    return key(a) + ">" + key(b)

func save() -> void:
    if storage.is_empty():
        return
    var cfg := ConfigFile.new()
    cfg.set_value("experience", "failures", failures)
    cfg.set_value("experience", "routes", routes)
    var result := cfg.save(storage)
    if result != OK:
        push_warning("NOV navigation experience could not persist: %s" % result)

func target(current: Vector2, goal: Vector2, probe: Callable = Callable()) -> Vector2:
    if last_goal.distance_to(goal) > 2.0:
        active = false
        visits.clear()
        trace.clear()
        last_goal = goal
    if active:
        return pending
    decision_serial += 1
    decision_evidence = {}
    source = current
    if trace.is_empty():
        trace.append(current)
    if probe.is_valid():
        return _anticipated_target(current, goal, probe)
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
    active = false
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

func _anticipated_target(current: Vector2, goal: Vector2, probe: Callable) -> Vector2:
    var direct := current.move_toward(goal, CELL_M)
    var address := key(goal) + "|" + key(current)
    var candidates: Array[Dictionary] = [{"point": direct, "bonus": 0.0, "source": "perception", "id": ""}]
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
    if not direct_clear and pending.distance_to(direct) > 0.05:
        anticipated_avoidances += 1
    active = true
    return pending
