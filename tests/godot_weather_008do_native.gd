extends SceneTree
const Weather = preload("res://world_map_weather.gd")
const Cycle = preload("res://world_map_day_cycle.gd")
func _init() -> void:
    call_deferred("_test")
func changed_pixels(a: Image,b: Image) -> int:
    var count := 0
    for y in range(a.get_height()):
        for x in range(a.get_width()):
            if a.get_pixel(x,y) != b.get_pixel(x,y):
                count += 1
    return count
func frame_image(viewport: SubViewport) -> Image:
    await process_frame
    await process_frame
    await RenderingServer.frame_post_draw
    return viewport.get_texture().get_image()
func _test() -> void:
    var viewport := SubViewport.new()
    viewport.size = Vector2i(320,240)
    viewport.own_world_3d = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var scene := Node3D.new()
    viewport.add_child(scene)
    var weather = Weather.new()
    scene.add_child(weather)
    weather.build()
    var camera := Camera3D.new()
    scene.add_child(camera)
    camera.current = true
    camera.far = 440.0
    camera.position = Vector3(0,20,0)
    var env := Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color("#90b9c4")
    var atmosphere := WorldEnvironment.new()
    atmosphere.environment = env
    scene.add_child(atmosphere)
    var light := DirectionalLight3D.new()
    scene.add_child(light)
    var cycle = Cycle.new()
    cycle.apply_clock({"schema":Cycle.SCHEMA,"source":"persisted_simulation_clock","world_id":"test","tick":3600,"tick_duration_ms":500,"logical_time_ms":1800000,"cycle_ms":3600000,"paused":true})
    var base: Vector3 = weather.cloud_center(0,Vector3.ZERO,Vector2.ZERO)
    var state := {"schema":Weather.SCHEMA,"source":"bounded_physical_simulation","world_id":"test","inference_influence":false,
        "time_ms":1800000,"tick_duration_ms":500,"generated_at_unix":int(Time.get_unix_time_from_system()),
        "wind_x_mps":3.0,"wind_z_mps":1.0,"cloud_offset_x_m":fposmod(-base.x,4096.0),"cloud_offset_z_m":fposmod(-160.0-base.z,4096.0),
        "cloud_coverage":0.8,"humidity":0.8,"temperature_c":20.0}
    # Recompute after world identity is known.
    state["cloud_coverage"] = 0.8
    assert(weather.apply_weather(state))
    base = weather.cloud_center(0,Vector3.ZERO,Vector2.ZERO)
    state["cloud_offset_x_m"] = fposmod(-base.x,4096.0)
    state["cloud_offset_z_m"] = fposmod(-160.0-base.z,4096.0)
    assert(weather.apply_weather(state))
    camera.look_at(Vector3(0,95,-160))
    cycle.present(env,light)
    weather.update_view(camera,cycle,20.0,env,light)
    weather._batch.visible = false
    var clear: Image = await frame_image(viewport)
    weather._batch.visible = true
    var cloudy: Image = await frame_image(viewport)
    var cloud_pixels := changed_pixels(clear,cloudy)
    assert(cloud_pixels > 100)
    cloudy.save_png("/home/etbra/008do-native-cloud.png")
    weather._batch.visible = false
    var mesh := CylinderMesh.new()
    mesh.height = 4.0
    mesh.top_radius = 0.15
    mesh.bottom_radius = 0.6
    mesh.radial_segments = 5
    var multi := MultiMesh.new()
    multi.transform_format = MultiMesh.TRANSFORM_3D
    multi.mesh = mesh
    multi.instance_count = 1
    multi.set_instance_transform(0,Transform3D(Basis.IDENTITY,Vector3(0,2,-9)))
    var grass := MultiMeshInstance3D.new()
    grass.multimesh = multi
    var material: ShaderMaterial = weather.grass_material(Color.GREEN,2.0)
    grass.material_override = material
    scene.add_child(grass)
    camera.position = Vector3(0,2,4)
    camera.look_at(Vector3(0,2,-9))
    material.set_shader_parameter("wind_world",Vector2(8,0))
    material.set_shader_parameter("phase_angle",0.0)
    var calm: Image = await frame_image(viewport)
    material.set_shader_parameter("phase_angle",PI*0.5)
    var wind: Image = await frame_image(viewport)
    var wind_pixels := changed_pixels(calm,wind)
    assert(wind_pixels > 5)
    assert(grass.multimesh.instance_count == 1)
    wind.save_png("/home/etbra/008do-native-wind.png")
    print("008DO_NATIVE_WEATHER_OK cloud_pixels=%d wind_pixels=%d" % [cloud_pixels,wind_pixels])
    viewport.free()
    quit(0)
