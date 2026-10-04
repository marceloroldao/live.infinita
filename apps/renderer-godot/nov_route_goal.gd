extends RefCounted
# Commit to an observed feed destination locally. No authoritative world writes.
const MAX_SECONDS := 180.0
const REACHED_M := 0.1
var active := false
var goal := Vector3.ZERO
var world_id := ""
var elapsed := 0.0
var serial := 0
var session := Crypto.new().generate_random_bytes(16).hex_encode()
var completed := 0
var expired := 0

func reset() -> void:
    active = false
    elapsed = 0.0

func identity() -> String:
    return session + ":" + str(serial) if active else ""

func choose(current: Vector3, latest: Vector3, delta: float, world: String) -> Vector3:
    if world != world_id:
        reset()
        world_id = world
    if active:
        elapsed += clampf(delta, 0.0, 0.1)
        if Vector2(current.x, current.z).distance_to(Vector2(goal.x, goal.z)) < REACHED_M:
            completed += 1
            reset()
        elif elapsed >= MAX_SECONDS:
            expired += 1
            print("NOV_ROUTE_REASSESS route=%s elapsed=%.1f" % [identity(), elapsed])
            reset()
    if not active and current.is_finite() and latest.is_finite():
        if Vector2(current.x, current.z).distance_to(Vector2(latest.x, latest.z)) < REACHED_M:
            return latest
        goal = latest
        active = true
        serial += 1
        print("NOV_ROUTE_COMMIT route=%s goal=(%.1f,%.1f)" % [identity(), goal.x, goal.z])
    return goal if active else current
