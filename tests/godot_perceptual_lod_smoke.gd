extends SceneTree

var failures := 0
var holder: Node3D

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func batch(_name: String, mesh: Mesh, _color: Color, budget: int) -> MultiMeshInstance3D:
    var mm := MultiMesh.new()
    mm.transform_format = MultiMesh.TRANSFORM_3D
    mm.mesh = mesh
    mm.instance_count = budget
    mm.visible_instance_count = budget
    var node := MultiMeshInstance3D.new()
    node.multimesh = mm
    holder.add_child(node)
    return node

func height(_x: float, _z: float) -> float:
    return 0.0

func allowed(_x: float, _z: float) -> bool:
    return true

func cell(value: float) -> int:
    return int(floor(value / 64.0))

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    holder = Node3D.new()
    root.add_child(holder)
    var script = load("res://world_map_perceptual_vegetation.gd")
    check(script != null, "Perceptual vegetation module must load")
    if script == null:
        quit(1)
        return

    var vegetation = script.new(
        Callable(self, "batch"),
        Callable(self, "height"),
        Callable(self, "allowed"),
        Callable(self, "cell"),
        1024.0,
    )
    vegetation.build(Vector3.ZERO, Vector3(0, 0, -1))
    vegetation.update_environment({
        "state_id": "lod-test",
        "regions": [{
            "region_id": "forest",
            "ecological_zone": "forest",
            "vegetation_density": 0.85,
            "tree_suitability": 0.82,
            "rock_exposure": 0.03,
            "snow_cover": 0.0,
        }],
    })
    vegetation.rebuild(Vector3.ZERO, Vector3(0, 0, -1), "forest", true)
    await process_frame

    var seed := 104729.0 * 3.0 + 130363.0 * 5.0
    var min_tree := 9999.0
    var max_tree := 0.0
    for i in range(500):
        var r: float = vegetation._tree_radius(seed, i)
        min_tree = minf(min_tree, r)
        max_tree = maxf(max_tree, r)

    var min_under := 9999.0
    var max_under := 0.0
    for i in range(500):
        var r: float = vegetation._undergrowth_radius(seed, i)
        min_under = minf(min_under, r)
        max_under = maxf(max_under, r)

    check(min_tree >= 23.5, "Procedural trees must stay outside hero foreground")
    check(max_tree <= 72.0, "Procedural trees must stay inside bounded background range")
    check(min_under >= 13.5, "Procedural undergrowth must leave near-NOV foreground clear")
    check(max_under <= 55.0, "Procedural undergrowth must stay bounded")

    print(
        "Perceptual LOD smoke: min_tree=", min_tree,
        " max_tree=", max_tree,
        " min_under=", min_under,
        " max_under=", max_under
    )
    holder.queue_free()
    await process_frame
    print("Perceptual LOD smoke: ", failures, " failures")
    quit(1 if failures else 0)
