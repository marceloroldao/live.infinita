extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false)
    await process_frame
    stage.get_node("LiveFeed").set_process(false)
    stage.get_node("LiveFeed").enabled = false
    var before: MeshInstance3D = stage._terrain(10,10,"clearing")
    var old: PackedFloat32Array = before.get_meta("resident_ground_heights")
    var origin: Vector2 = stage._layout.tile_origin(10,10)
    var center := origin + Vector2(64,32)
    stage._cognitive_terrain._anchors = [{"position":center,"radius":200.0,"bias":12.0}]
    check(absf(stage._proposed_raw_height(center.x,center.y)-stage._raw_height(center.x,center.y))>1,"Fixture must change inferred elevation")
    var after: MeshInstance3D = stage._terrain(11,10,"clearing")
    var fresh: PackedFloat32Array = after.get_meta("resident_ground_heights")
    for z in range(9):
        check(absf(old[z*9+8]-fresh[z*9])<0.00001,"Shared edge survives inference revision")
    var rebuilt: MeshInstance3D = stage._terrain(10,10,"clearing")
    check(rebuilt.get_meta("resident_ground_heights")==old,"Eviction and rebuild retain physical ground")
    var vertices: PackedVector3Array = after.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
    for vertex in vertices:
        check(absf(vertex.y-stage._height(vertex.x,vertex.z))<0.00001,"Visible and sensed surface coincide")
    var foot := Vector2(origin.x+61.5,origin.y+31.7)
    var y: float = stage._height(foot.x,foot.y)
    stage._cognitive_terrain._anchors[0]["bias"] = -12.0
    check(is_equal_approx(y,stage._height(foot.x,foot.y)),"No floor movement under observer")
    before.free()
    after.free()
    rebuilt.free()
    stage.queue_free()
    await process_frame
    print("Ground continuity smoke: ",failures," failures")
    quit(1 if failures else 0)
