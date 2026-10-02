extends SceneTree

class FakeFeatures:
    extends RefCounted
    func walk_height(_x: float, _z: float) -> float:
        return 0.0

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func child_count_of_type(root: Node, class_type: String) -> int:
    var total := 0
    for child in root.get_children():
        if child.is_class(class_type):
            total += 1
    return total

func find_named(root: Node, wanted: String) -> Node:
    for child in root.get_children():
        if str(child.name) == wanted:
            return child
    return null

func regions_fixture() -> Array:
    var regions: Array = []
    for i in range(16):
        regions.append({
            "id": "region_%02d" % i,
            "center": {
                "x": 640.0 + float(i % 4) * 20.0,
                "y": 360.0 + float(i / 4) * 20.0,
            },
            "radius": 18.0 + float(i % 3) * 3.0,
            "metadata": {"label": "Region %02d" % i},
        })
    return regions

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var host := Node3D.new()
    root.add_child(host)
    var script = load("res://world_map_live_visual.gd")
    var live = script.new(host, FakeFeatures.new(), {
        "grid_size": 32,
        "tile_size_m": 64,
    })
    live.build()

    var regions := regions_fixture()
    var count: int = live.update_regions(regions, "region_05")
    check(count == 16, "Logical region count must remain 16")
    check(live._region_root.get_child_count() == 5, "Overlay must contain one ring batch plus four labels")
    check(child_count_of_type(live._region_root, "MeshInstance3D") == 1, "Rings must use one MeshInstance3D")
    check(child_count_of_type(live._region_root, "Label3D") == 4, "Labels must be bounded to four")
    check(find_named(live._region_root, "RegionLabel_region_05") != null, "Current region label must always remain")

    var rings = find_named(live._region_root, "RegionRings")
    check(rings is MeshInstance3D, "RegionRings batch must exist")
    if rings is MeshInstance3D:
        check(rings.mesh != null, "RegionRings must have mesh")
        if rings.mesh != null:
            check(rings.mesh.get_surface_count() == 2, "Current + normal regions must use two surfaces")

    var unchanged: int = live.update_regions(regions, "region_05")
    check(unchanged == 16, "Stable signature must preserve logical count")
    check(live._region_root.get_child_count() == 5, "Stable update must not duplicate overlay nodes")

    var switched: int = live.update_regions(regions, "region_15")
    check(switched == 16, "Current-region switch must preserve logical count")
    check(find_named(live._region_root, "RegionLabel_region_15") != null, "New current region label must be present")
    check(live._region_root.get_child_count() == 5, "Current-region switch keeps bounded overlay")

    host.free()
    print("Region visual batching smoke: ", failures, " failures")
    quit(1 if failures else 0)
