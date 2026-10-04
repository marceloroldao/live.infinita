extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false)
    await process_frame
    var feed = stage.get_node("LiveFeed")
    feed.enabled = false
    feed.set_process(false)
    # The old raw height changes scale at x=175. Feet must follow the triangle
    # interpolation there, rather than dropping below its visible face.
    for point in [Vector2(174, -100), Vector2(175.5, -100), Vector2(177, -100), Vector2(202.5, -75)]:
        var x0: float = floor((point.x + 1024.0) / 8.0) * 8.0 - 1024.0
        var z0: float = floor((point.y + 1024.0) / 8.0) * 8.0 - 1024.0
        var u: float = (point.x - x0) / 8.0
        var v: float = (point.y - z0) / 8.0
        var a: float = stage._raw_height(x0, z0)
        var b: float = stage._raw_height(x0 + 8, z0)
        var c: float = stage._raw_height(x0, z0 + 8)
        var d: float = stage._raw_height(x0 + 8, z0 + 8)
        var expected: float = a + u * (b - a) + v * (c - a) if u + v <= 1 else d + (1-u)*(c-d)+(1-v)*(b-d)
        check(absf(stage._height(point.x, point.y) - expected) < 0.0001, "Feet must match rendered triangle")
    stage._position = Vector3(174, stage._height(174, -100), -100)
    stage._sync_tiles()
    stage._rebuild_horizon_ground()
    var arrays = stage._horizon_ground.mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var cx: int = stage._cell(stage._position.x)
    var cz: int = stage._cell(stage._position.z)
    var min_x: float = float(maxi(0,cx-1))*64-1024
    var max_x: float = float(mini(32,cx+2))*64-1024
    var min_z: float = float(maxi(0,cz-1))*64-1024
    var max_z: float = float(mini(32,cz+2))*64-1024
    for i in range(0, vertices.size(), 3):
        var center: Vector3 = (vertices[i]+vertices[i+1]+vertices[i+2])/3.0
        check(not (center.x > min_x and center.x < max_x and center.z > min_z and center.z < max_z),
            "Coarse horizon must not overlap local ground")
    stage._follow_camera()
    var camera_ground: float = stage._height(stage._camera.position.x,stage._camera.position.z)
    check(stage._camera.position.y >= camera_ground+1.85, "Camera must stay above rendered local surface")
    stage.queue_free()
    await process_frame
    print("Ground surface smoke: ",failures," failures")
    quit(1 if failures else 0)
