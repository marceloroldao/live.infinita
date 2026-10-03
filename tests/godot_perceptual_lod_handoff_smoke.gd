extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func height(_x: float, _z: float) -> float:
    return 0.0

func allowed(_x: float, _z: float) -> bool:
    return true

func cell(value: float) -> int:
    return int(floor(value / 64.0))

func batch_factory(
    name: String,
    mesh: Mesh,
    _color: Color,
    budget: int,
) -> MultiMeshInstance3D:
    var mm := MultiMesh.new()
    mm.transform_format = MultiMesh.TRANSFORM_3D
    mm.mesh = mesh
    mm.instance_count = budget
    mm.visible_instance_count = 0
    var node := MultiMeshInstance3D.new()
    node.name = name
    node.multimesh = mm
    root.add_child(node)
    return node

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var script = load("res://world_map_perceptual_vegetation.gd")
    check(script != null, "Procedural vegetation module must load")
    if script == null:
        quit(1)
        return

    var procedural = script.new(
        Callable(self, "batch_factory"),
        Callable(self, "height"),
        Callable(self, "allowed"),
        Callable(self, "cell"),
        1024.0,
    )

    procedural.set_hero_nearfield_enabled(false)
    check(not procedural.hero_nearfield_enabled(), "Fallback mode must keep procedural nearfield")
    check(absf(procedural._tree_inner_m - 7.5) < 0.01, "Fallback tree radius must be legacy radius")
    check(absf(procedural._undergrowth_inner_m - 4.5) < 0.01, "Fallback undergrowth radius must be legacy radius")

    procedural.set_hero_nearfield_enabled(true)
    check(procedural.hero_nearfield_enabled(), "Vendor mode must enable nearfield handoff")
    check(absf(procedural._tree_inner_m - 25.0) < 0.01, "Vendor tree handoff must start at 25m")
    check(absf(procedural._undergrowth_inner_m - 20.0) < 0.01, "Vendor undergrowth handoff must start at 20m")

    procedural.build(Vector3.ZERO, Vector3(0, 0, -1))
    check(procedural.tree_visible_count() >= 0, "Procedural batch must still build")
    check(procedural.undergrowth_visible_count() >= 0, "Procedural undergrowth must still build")

    print("Perceptual LOD handoff smoke: ", failures, " failures")
    quit(1 if failures else 0)
