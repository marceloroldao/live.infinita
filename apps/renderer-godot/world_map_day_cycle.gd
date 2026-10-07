extends RefCounted
# Presentation only. Clock authority stays in the persistent server clock.
const SCHEMA := "live-infinita-sky-clock/v1"
var _world_id := ""
var _tick := -1
var _duration := 500.0
var _logical_ms := 0.0
var _cycle_ms := 3600000.0
var _elapsed := 0.0
var _paused := false
var _synced := false

func apply_clock(value: Dictionary) -> bool:
    if str(value.get("schema", "")) != SCHEMA or str(value.get("source", "")) != "persisted_simulation_clock":
        return false
    var world_id := str(value.get("world_id", ""))
    if world_id.is_empty() or typeof(value.get("paused")) != TYPE_BOOL:
        return false
    for key in ["tick", "tick_duration_ms", "logical_time_ms", "cycle_ms"]:
        var raw = value.get(key)
        if typeof(raw) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(raw)) or float(raw) != floor(float(raw)):
            return false
    var tick := int(value["tick"])
    var duration := float(value["tick_duration_ms"])
    var logical_ms := float(value["logical_time_ms"])
    var cycle_ms := float(value["cycle_ms"])
    if tick < 0 or tick > 1000000000000 or duration < 1.0 or duration > 60000.0 or cycle_ms != 3600000.0:
        return false
    if logical_ms != float(tick) * duration:
        return false
    if world_id == _world_id and tick < _tick:
        return false
    if _synced and world_id == _world_id and tick == _tick and duration == _duration and bool(value["paused"]) == _paused:
        return true
    _world_id = world_id
    _tick = tick
    _duration = duration
    _logical_ms = logical_ms
    _cycle_ms = cycle_ms
    _paused = bool(value["paused"])
    _elapsed = 0.0
    _synced = true
    return true

func advance(delta: float) -> void:
    if _synced and not _paused and is_finite(delta) and delta > 0.0:
        # Stop extrapolating after one tick if updates stop arriving.
        _elapsed = minf(_duration / 1000.0, _elapsed + delta)

func sample() -> Dictionary:
    if not _synced:
        return {"synced": false, "phase": 0.5, "daylight": 1.0, "sun_elevation": 1.0}
    var phase := fposmod(_logical_ms + _elapsed * 1000.0, _cycle_ms) / _cycle_ms
    var elevation := sin(phase * TAU - PI * 0.5)
    var daylight := smoothstep(-0.16, 0.20, elevation)
    return {"synced": true, "phase": phase, "daylight": daylight, "sun_elevation": elevation}

func present(env: Environment, light: DirectionalLight3D) -> void:
    var state := sample()
    var day := float(state["daylight"])
    var elevation := float(state["sun_elevation"])
    var twilight := (1.0 - smoothstep(0.0, 0.28, absf(elevation))) if bool(state["synced"]) else 0.0
    var sky := Color("#111d37").lerp(Color("#90b9c4"), day).lerp(Color("#bc8269"), twilight * 0.45)
    env.background_color = sky
    env.ambient_light_color = Color("#7184ad").lerp(Color("#d6e2d4"), day)
    env.ambient_light_energy = lerpf(0.42, 1.0, day)
    env.fog_light_color = Color("#243551").lerp(Color("#abc4c1"), day).lerp(Color("#b88d77"), twilight * 0.3)
    env.fog_light_energy = lerpf(0.30, 0.72, day)
    light.light_energy = lerpf(0.13, 1.25, day)
    light.light_color = Color("#a5b9e0").lerp(Color.WHITE, day).lerp(Color("#ffc18c"), twilight * 0.4)
    # Use a gentle moonlike fill at night; no claim of a memory-linked Moon yet.
    light.rotation_degrees = Vector3(-lerpf(15.0, 65.0, maxf(0.0, elevation)), 27.0 + float(state["phase"]) * 180.0, 0.0)
