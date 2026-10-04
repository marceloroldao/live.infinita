extends RefCounted
# Local renderer experience only; no World State or Memoria.ia authority.
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

func target(current: Vector2, goal: Vector2) -> Vector2:
    if last_goal.distance_to(goal) > 2.0:
        active = false
        visits.clear()
        trace.clear()
        last_goal = goal
    if active:
        return pending
    source = current
    if trace.is_empty():
        trace.append(current)
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
