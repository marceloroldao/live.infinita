extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func flat_height(_x: float, _z: float) -> float:
    return 0.0

func count_type(root: Node, class_type: String) -> int:
    var total := 1 if root.is_class(class_type) else 0
    for child in root.get_children():
        total += count_type(child, class_type)
    return total

func find_named(root: Node, wanted: String) -> Node:
    if str(root.name) == wanted:
        return root
    for child in root.get_children():
        var found := find_named(child, wanted)
        if found != null:
            return found
    return null

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var feature_script = load("res://world_map_features.gd")
    var features = feature_script.new(Callable(self, "flat_height"), 1024.0)

    var bridge := Node3D.new()
    root.add_child(bridge)
    features._bridge(bridge)

    var planks = find_named(bridge, "BridgePlanks")
    var posts = find_named(bridge, "BridgePosts")
    check(planks is MultiMeshInstance3D, "Bridge planks must use MultiMesh")
    check(posts is MultiMeshInstance3D, "Bridge posts must use MultiMesh")
    if planks is MultiMeshInstance3D:
        check(planks.multimesh.instance_count == 15, "Bridge must preserve 15 planks")
    if posts is MultiMeshInstance3D:
        check(posts.multimesh.instance_count == 10, "Bridge must preserve 10 posts")
    check(count_type(bridge, "GeometryInstance3D") == 5, "Bridge visuals should collapse to five draw objects")
    check(count_type(bridge, "StaticBody3D") == 2, "Bridge rail collision bodies must remain")

    var stones := Node3D.new()
    root.add_child(stones)
    features._special_landmark(stones, Vector3.ZERO, "stone_circle")
    var standing = find_named(stones, "StandingStones")
    check(standing is MultiMeshInstance3D, "Stone circle must use MultiMesh")
    if standing is MultiMeshInstance3D:
        check(standing.multimesh.instance_count == 8, "Stone circle must preserve eight stones")
    check(count_type(stones, "GeometryInstance3D") == 1, "Stone circle should use one draw object")
    check(find_named(stones, "StandingStone_0") != null, "Stone circle compatibility marker")

    bridge.free()
    stones.free()
    print("Static feature batching smoke: ", failures, " failures")
    quit(1 if failures else 0)
