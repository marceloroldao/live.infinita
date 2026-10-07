extends Node3D
const SCHEMA := "live-infinita-physical-weather/v1"
const CLOUDS := 24
const CLOUD_TILE_M := 1024.0
var _state: Dictionary = {}
var _wind := Vector2.ZERO
var _coverage := 0.0
var _batch: MultiMeshInstance3D
var _material: StandardMaterial3D
var _grass_materials: Array[ShaderMaterial] = []
var _camera: Camera3D
var _centers: Array[Vector3] = []
var _last_world := ""
var _last_time := -1

func _init() -> void:
    name = "PhysicalWeather"

func build() -> void:
    var mesh := SphereMesh.new()
    mesh.radius = 1.0
    mesh.height = 2.0
    mesh.radial_segments = 8
    mesh.rings = 3
    var multi := MultiMesh.new()
    multi.transform_format = MultiMesh.TRANSFORM_3D
    multi.mesh = mesh
    multi.instance_count = CLOUDS * 3
    _batch = MultiMeshInstance3D.new()
    _batch.name = "AdvectedClouds"
    _batch.multimesh = multi
    _batch.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    _material = StandardMaterial3D.new()
    _material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    _material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    _material.albedo_color = Color(0.9,0.93,0.95,0.0)
    _material.disable_fog = true
    _batch.material_override = _material
    _batch.visible = false
    add_child(_batch)

func grass_material(color: Color, half_height: float = 0.7) -> ShaderMaterial:
    var shader := Shader.new()
    shader.code = """shader_type spatial;
render_mode unshaded;
uniform vec4 base_color : source_color;
uniform vec2 wind_world = vec2(0.0);
uniform float phase_angle = 0.0;
uniform float half_height = 0.7;
void vertex() {
    float anchor = clamp((VERTEX.y + half_height) / (2.0 * half_height), 0.0, 1.0);
    float sway = sin(phase_angle + float(INSTANCE_ID) * 0.37);
    vec3 local_wind = inverse(mat3(MODEL_MATRIX)) * vec3(wind_world.x, 0.0, wind_world.y);
    VERTEX += local_wind * (0.015 * anchor * anchor * sway);
}
void fragment() { ALBEDO = base_color.rgb; }
"""
    var material := ShaderMaterial.new()
    material.shader = shader
    material.set_shader_parameter("base_color",color)
    material.set_shader_parameter("half_height",half_height)
    _grass_materials.append(material)
    return material

func apply_weather(value: Dictionary) -> bool:
    if str(value.get("schema","")) != SCHEMA or str(value.get("source","")) != "bounded_physical_simulation" or value.get("inference_influence") != false:
        return false
    var world := str(value.get("world_id",""))
    if world.is_empty():
        return false
    for key in ["time_ms","tick_duration_ms","generated_at_unix","wind_x_mps","wind_z_mps","cloud_offset_x_m","cloud_offset_z_m","cloud_coverage","humidity","temperature_c"]:
        var number = value.get(key)
        if typeof(number) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(number)):
            return false
    var stamp := float(value["generated_at_unix"])
    if Time.get_unix_time_from_system()-stamp > 180.0 or stamp-Time.get_unix_time_from_system() > 30.0:
        return false
    if float(value["time_ms"]) < 0.0 or float(value["time_ms"]) != floor(float(value["time_ms"])) or float(value["tick_duration_ms"]) < 1.0 or float(value["tick_duration_ms"]) > 60000.0:
        return false
    if absf(float(value["wind_x_mps"])) > 8.0 or absf(float(value["wind_z_mps"])) > 8.0:
        return false
    if float(value["cloud_coverage"]) < 0.0 or float(value["cloud_coverage"]) > 1.0 or float(value["humidity"]) < 0.0 or float(value["humidity"]) > 1.0:
        return false
    for key in ["cloud_offset_x_m","cloud_offset_z_m"]:
        if float(value[key]) < 0.0 or float(value[key]) > 4096.0:
            return false
    if world == _last_world and int(value["time_ms"]) < _last_time:
        return false
    if world != _last_world:
        _wind = Vector2.ZERO
        _coverage = 0.0
    _state = value.duplicate(true)
    _last_world = world
    _last_time = int(value["time_ms"])
    return true

func cloud_center(index: int, camera_position: Vector3, offset: Vector2) -> Vector3:
    # Absolute world tiling; wraps only beyond the camera far plane.
    var digest := ("%s:cloud:%d" % [_last_world,index]).sha256_text()
    var x := float(digest.substr(0,8).hex_to_int()) / 4294967295.0 * CLOUD_TILE_M
    var z := float(digest.substr(8,8).hex_to_int()) / 4294967295.0 * CLOUD_TILE_M
    var y := 95.0 + float(index % 7) * 5.0
    return Vector3(camera_position.x + fposmod(x+offset.x-camera_position.x+CLOUD_TILE_M*0.5,CLOUD_TILE_M)-CLOUD_TILE_M*0.5,
        y,camera_position.z + fposmod(z+offset.y-camera_position.z+CLOUD_TILE_M*0.5,CLOUD_TILE_M)-CLOUD_TILE_M*0.5)

func update_view(camera: Camera3D, cycle: RefCounted, delta: float, env: Environment, light: DirectionalLight3D) -> void:
    if _batch == null or camera == null:
        return
    _camera = camera
    var sample: Dictionary = cycle.sample()
    var valid: bool = not _state.is_empty() and bool(sample["synced"]) and cycle._world_id == _last_world
    if valid:
        valid = Time.get_unix_time_from_system()-float(_state["generated_at_unix"]) <= 180.0
    var target_wind := Vector2(float(_state.get("wind_x_mps",0.0)),float(_state.get("wind_z_mps",0.0))) if valid else Vector2.ZERO
    var target_coverage := float(_state.get("cloud_coverage",0.0)) if valid else 0.0
    var blend := 1.0-exp(-maxf(0.0,delta)/3.0)
    _wind = _wind.lerp(target_wind,blend)
    _coverage = lerpf(_coverage,target_coverage,blend)
    var logical_ms := float(cycle._logical_ms) + float(cycle._elapsed)*1000.0
    var extrapolated := clampf((logical_ms-float(_state.get("time_ms",logical_ms)))/1000.0,0.0,5.0) if valid else 0.0
    var offset := Vector2(float(_state.get("cloud_offset_x_m",0.0)),float(_state.get("cloud_offset_z_m",0.0))) + target_wind*extrapolated
    var phase := fposmod(logical_ms/1000.0*0.8,TAU)
    for material in _grass_materials:
        material.set_shader_parameter("wind_world",_wind)
        material.set_shader_parameter("phase_angle",phase)
    _batch.visible = _coverage > 0.002
    var color := Color("#64718b").lerp(Color("#e9edf0"),float(sample["daylight"]))
    color.a = _coverage * 0.65
    _material.albedo_color = color
    _centers.clear()
    for i in range(CLOUDS):
        var center := cloud_center(i,camera.global_position,offset)
        _centers.append(center)
        for puff in range(3):
            var scale := Vector3(19.0+float(i%4)*3.0,6.0+float(puff),14.0+float(i%3)*2.0)
            var location := center+Vector3(float(puff-1)*17.0,float(puff%2)*3.0,0.0)
            _batch.multimesh.set_instance_transform(i*3+puff,Transform3D(Basis.IDENTITY.scaled(scale),location))
    # Apply after daily lighting; preserve sufficient night fill.
    if env != null and light != null:
        light.light_energy *= 1.0-0.30*_coverage
        env.ambient_light_energy *= 1.0-0.12*_coverage
