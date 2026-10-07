extends SceneTree
const Cycle = preload("res://world_map_day_cycle.gd")
func _init() -> void:
    var cycle = Cycle.new()
    var clock := {"schema": "live-infinita-sky-clock/v1", "source": "persisted_simulation_clock", "world_id": "test", "tick": 0, "tick_duration_ms": 500, "logical_time_ms": 0, "cycle_ms": 3600000, "paused": false}
    assert(not cycle.sample()["synced"])
    assert(cycle.apply_clock(clock))
    assert(cycle.sample()["daylight"] == 0.0)
    cycle.advance(100.0)
    assert(float(cycle.sample()["phase"]) <= 500.0 / 3600000.0)
    var older := clock.duplicate()
    clock["tick"] = 3600; clock["logical_time_ms"] = 1800000
    assert(cycle.apply_clock(clock))
    assert(cycle.sample()["daylight"] == 1.0)
    assert(not cycle.apply_clock(older))
    var other = Cycle.new()
    assert(other.apply_clock(clock))
    assert(other.sample() == cycle.sample())
    clock["paused"] = true
    assert(cycle.apply_clock(clock))
    var phase = cycle.sample()["phase"]
    cycle.advance(300.0)
    assert(cycle.sample()["phase"] == phase)
    clock["tick"] = true
    assert(not cycle.apply_clock(clock))
    var env := Environment.new()
    var light := DirectionalLight3D.new()
    cycle.present(env,light)
    assert(light.light_energy == 1.25)
    var night = Cycle.new()
    assert(night.apply_clock(older))
    night.present(env,light)
    assert(light.light_energy > 0.0 and light.light_energy < 0.2)
    assert(env.ambient_light_energy >= 0.4)
    var feed = preload("res://world_map_live_feed.gd").new()
    feed.sky_clock_received.connect(Callable(cycle, "apply_clock"))
    older["world_id"] = "packet-world"
    var packet := {"type": "world_state", "world": {"world_id": "packet-world", "interest": {}, "entities": []}, "delivery": {"observer": {}, "sky_clock": older}}
    feed._accept_packet(JSON.stringify(packet))
    assert(cycle._world_id == "packet-world")
    assert(cycle.sample()["daylight"] == 0.0)
    older["world_id"] = "wrong-world"
    feed._accept_packet(JSON.stringify(packet))
    assert(cycle._world_id == "packet-world")
    feed.free()
    light.free()
    print("008DM_DAY_CYCLE_OK")
    quit(0)
