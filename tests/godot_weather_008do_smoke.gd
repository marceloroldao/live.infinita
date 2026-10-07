extends SceneTree
const Weather = preload("res://world_map_weather.gd")
const Cycle = preload("res://world_map_day_cycle.gd")
func _init() -> void:
    call_deferred("_test")
func _test() -> void:
    var weather = Weather.new()
    root.add_child(weather)
    weather.build()
    var material = weather.grass_material(Color.GREEN,0.475)
    var state := {"schema":Weather.SCHEMA,"source":"bounded_physical_simulation","world_id":"test","inference_influence":false,
        "time_ms":0,"tick_duration_ms":500,"generated_at_unix":int(Time.get_unix_time_from_system()),
        "wind_x_mps":3.0,"wind_z_mps":1.0,"cloud_offset_x_m":0.0,"cloud_offset_z_m":0.0,
        "cloud_coverage":0.5,"humidity":0.8,"temperature_c":20.0}
    assert(weather.apply_weather(state))
    var camera := Camera3D.new()
    root.add_child(camera)
    var cycle = Cycle.new()
    assert(cycle.apply_clock({"schema":Cycle.SCHEMA,"source":"persisted_simulation_clock","world_id":"test","tick":0,"tick_duration_ms":500,"logical_time_ms":0,"cycle_ms":3600000,"paused":true}))
    var env := Environment.new()
    var light := DirectionalLight3D.new()
    cycle.present(env,light)
    var before := light.light_energy
    weather.update_view(camera,cycle,10.0,env,light)
    assert(weather._batch.visible)
    assert(weather._centers.size() == Weather.CLOUDS)
    assert(light.light_energy > 0.0 and light.light_energy < before)
    assert(weather._wind.x > 0.0)
    assert(material.get_shader_parameter("wind_world").x > 0.0)
    var phase = material.get_shader_parameter("phase_angle")
    weather.update_view(camera,cycle,1.0,null,null)
    assert(material.get_shader_parameter("phase_angle") == phase)
    var center = weather.cloud_center(0,Vector3.ZERO,Vector2.ZERO)
    assert(center.is_equal_approx(weather.cloud_center(0,Vector3(1,0,1),Vector2.ZERO)))
    var moved = weather.cloud_center(0,Vector3.ZERO,Vector2(3,1))
    assert((moved-center).is_equal_approx(Vector3(3,0,1)))
    var invalid := state.duplicate(true)
    invalid["wind_x_mps"] = NAN
    assert(not weather.apply_weather(invalid))
    invalid = state.duplicate(true)
    invalid["inference_influence"] = true
    assert(not weather.apply_weather(invalid))
    invalid = state.duplicate(true)
    invalid["generated_at_unix"] -= 181
    assert(not weather.apply_weather(invalid))
    var feed = preload("res://world_map_live_feed.gd").new()
    feed.physical_weather_received.connect(Callable(weather,"apply_weather"))
    state["world_id"] = "transport"
    feed._accept_packet(JSON.stringify({"type":"world_state","world":{"world_id":"transport","interest":{},"entities":[]},"delivery":{"observer":{},"physical_weather":state}}))
    assert(weather._last_world == "transport")
    feed.free();camera.free();weather.free();light.free()
    print("008DO_WEATHER_OK")
    quit(0)
