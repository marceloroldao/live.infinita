extends SceneTree
const MemorySky = preload("res://world_map_memory_sky.gd")
const Cycle = preload("res://world_map_day_cycle.gd")
func _init() -> void:
    call_deferred("_test")
func _test() -> void:
    var sky = MemorySky.new()
    root.add_child(sky)
    sky.build()
    var now := int(Time.get_unix_time_from_system())
    var id := "external-episode:" + "a".repeat(64)
    var projection := {"schema":MemorySky.SCHEMA,"source":"confirmed_local_memoria_aggregate_records","world_id":"test","generated_at_unix":now,
        "stars":[{"memory_id":id,"birth_tick":10,"payload_bytes":1000,"distance":2.0,"brightness":0.3,"confirmed":true}],
        "bodies":[{"body":"sun","memory_id":"structural-event:"+"b".repeat(40),"provenance":"world_celestial_definition","confirmed":true},
                  {"body":"moon","memory_id":"structural-event:"+"c".repeat(40),"provenance":"world_celestial_definition","confirmed":true}]}
    assert(sky.apply_projection(projection))
    var direction := sky.direction_for(id)
    var other = MemorySky.new()
    assert(direction == other.direction_for(id))
    other.free()
    assert(is_equal_approx(direction.length(),1.0))
    var camera := Camera3D.new()
    root.add_child(camera)
    var cycle = Cycle.new()
    assert(cycle.apply_clock({"schema":Cycle.SCHEMA,"source":"persisted_simulation_clock","world_id":"test","tick":0,"tick_duration_ms":500,"logical_time_ms":0,"cycle_ms":3600000,"paused":true}))
    sky.update_view(camera,cycle,5.0)
    assert(sky._moon.visible and not sky._sun.visible)
    assert(sky._batch.visible and sky._entries[id]["fade"] > 0.0)
    var fade = sky._entries[id]["fade"]
    assert(sky.apply_projection(projection))
    assert(sky._entries[id]["fade"] == fade)
    var invalid := projection.duplicate(true)
    invalid["stars"][0]["confirmed"] = false
    assert(not sky.apply_projection(invalid))
    assert(sky._entries[id]["fade"] == fade)
    invalid = projection.duplicate(true)
    invalid["generated_at_unix"] = now - 181
    assert(not sky.apply_projection(invalid))
    invalid = projection.duplicate(true)
    invalid["stars"][0]["brightness"] = NAN
    assert(not sky.apply_projection(invalid))
    cycle._logical_ms = 1800000.0
    sky.update_view(camera,cycle,5.0)
    assert(sky._sun.visible and not sky._moon.visible)
    assert(not sky._batch.visible and sky._entries[id]["fade"] == 0.0)
    camera.free();sky.free()
    print("008DN_MEMORY_SKY_OK")
    quit(0)
