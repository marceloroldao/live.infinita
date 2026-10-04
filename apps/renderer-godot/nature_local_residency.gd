extends RefCounted
# Positions belong to the terrain, never to the observer or camera heading.
# Loaded records are immutable until outside the retention radius.
const PROTECTED_RADIUS_M := 45.0
var records: Dictionary = {}
var _initialized := false

func sample_noise(x: int, z: int, salt: int) -> float:
    var value := (x * 73856093) ^ (z * 19349663) ^ (salt * 83492791)
    value = ((value ^ (value >> 13)) * 1274126177) & 0x7fffffff
    return float(value) / 2147483647.0

func update(
    origin: Vector3, budget: int, density: float, spacing: float,
    load_radius: float, retain_radius: float, salt: int,
    half_m: float, allowed: Callable, minimum_spawn_distance: float = 8.0,
) -> Array:
    var center := Vector2(origin.x, origin.z)
    var spawn_minimum := maxf(minimum_spawn_distance, PROTECTED_RADIUS_M) if _initialized else minimum_spawn_distance
    for key in records.keys():
        var record: Dictionary = records[key]
        if center.distance_to(record["point"]) > retain_radius:
            records.erase(key)
    var target := clampi(roundi(float(budget) * density), 0, budget)
    var candidates: Array = []
    var lower := Vector2i(floori((center.x - load_radius) / spacing), floori((center.y - load_radius) / spacing))
    var upper := Vector2i(ceili((center.x + load_radius) / spacing), ceili((center.y + load_radius) / spacing))
    for z in range(lower.y, upper.y + 1):
        for x in range(lower.x, upper.x + 1):
            var key := "%d:%d" % [x, z]
            if records.has(key) or sample_noise(x, z, salt + 7) >= density:
                continue
            var point := Vector2(
                (float(x) + 0.2 + 0.6 * sample_noise(x, z, salt + 1)) * spacing,
                (float(z) + 0.2 + 0.6 * sample_noise(x, z, salt + 2)) * spacing
            )
            var distance := center.distance_to(point)
            if distance > load_radius or distance < spawn_minimum:
                continue
            if absf(point.x) > half_m - 8.0 or absf(point.y) > half_m - 8.0:
                continue
            if not bool(allowed.call(point.x, point.y)):
                continue
            candidates.append({"key": key, "point": point, "distance": distance,
                "noise": sample_noise(x, z, salt + 3)})
    candidates.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        if a["distance"] == b["distance"]:
            return str(a["key"]) < str(b["key"])
        return a["distance"] < b["distance"])
    for candidate in candidates:
        if records.size() >= target:
            break
        records[candidate["key"]] = candidate
    _initialized = true
    return records.values()
