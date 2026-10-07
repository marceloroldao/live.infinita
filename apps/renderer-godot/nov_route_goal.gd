extends RefCounted
# Commit to an observed feed destination locally. No authoritative world writes.
const MAX_SECONDS := 180.0
const REACHED_M := 0.1
const HARD_LIMIT_SECONDS := 900.0
var last_ended_id := ""
var last_ended_reason := ""
var total_elapsed := 0.0
var _seen_cells: Dictionary = {}
var active := false
var goal := Vector3.ZERO
var world_id := ""
var elapsed := 0.0
var serial := 0
var session := Crypto.new().generate_random_bytes(16).hex_encode()
var completed := 0
var expired := 0
var adjusted := 0
var rejected := 0
var _rejected_latest := Vector3(INF,INF,INF)
var _rejected_at := -10000

func reset() -> void:
    active = false
    elapsed = 0.0
    total_elapsed = 0.0
    _seen_cells.clear()
    _rejected_latest = Vector3(INF,INF,INF)

func identity() -> String:
    return session + ":" + str(serial) if active else ""

func choose(current: Vector3, latest: Vector3, delta: float, world: String, resolve: Callable = Callable()) -> Vector3:
    last_ended_id = ""
    last_ended_reason = ""
    if world != world_id:
        if active:
            last_ended_id = identity()
            last_ended_reason = "world_changed"
        reset()
        world_id = world
    if active:
        elapsed += clampf(delta, 0.0, 0.1)
        total_elapsed += clampf(delta,0.0,0.1)
        var cell := Vector2i(floori(current.x/8.0),floori(current.z/8.0))
        if not _seen_cells.has(cell):
            _seen_cells[cell] = true
            elapsed = 0.0
        while _seen_cells.size()>4096:
            _seen_cells.erase(_seen_cells.keys()[0])
        if Vector2(current.x, current.z).distance_to(Vector2(goal.x, goal.z)) < REACHED_M:
            completed += 1
            reset()
        elif elapsed >= MAX_SECONDS or total_elapsed>=HARD_LIMIT_SECONDS:
            expired += 1
            last_ended_id = identity()
            last_ended_reason = "goal_hard_timeout" if total_elapsed>=HARD_LIMIT_SECONDS else "goal_idle_timeout"
            print("NOV_ROUTE_REASSESS route=%s idle=%.1f total=%.1f" % [identity(), elapsed,total_elapsed])
            reset()
    if not active and current.is_finite() and latest.is_finite():
        if Vector2(current.x, current.z).distance_to(Vector2(latest.x, latest.z)) < REACHED_M:
            return latest
        if latest.distance_to(_rejected_latest)<0.1 and Time.get_ticks_msec()-_rejected_at<5000:
            return current
        var destination := latest
        if resolve.is_valid():
            var result: Dictionary = resolve.call(latest)
            if not bool(result.get("allowed",false)):
                rejected += 1
                _rejected_latest = latest
                _rejected_at = Time.get_ticks_msec()
                print("NOV_ROUTE_REJECT reason=%s" % str(result.get("reason","unwalkable")))
                return current
            destination = result.get("position",latest)
            if bool(result.get("adjusted",false)):
                adjusted += 1
                print("NOV_ROUTE_ADJUST requested=(%.1f,%.1f) resolved=(%.1f,%.1f)" % [latest.x,latest.z,destination.x,destination.z])
        goal = destination
        if Vector2(current.x,current.z).distance_to(Vector2(goal.x,goal.z))<REACHED_M:
            return current
        _seen_cells[Vector2i(floori(current.x/8.0),floori(current.z/8.0))] = true
        active = true
        serial += 1
        print("NOV_ROUTE_COMMIT route=%s goal=(%.1f,%.1f)" % [identity(), goal.x, goal.z])
    return goal if active else current
