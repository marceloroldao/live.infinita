extends SceneTree
const Residency = preload("res://nature_local_residency.gd")
const Assets = preload("res://world_map_perceptual_assets.gd")
var failures := 0
func check(ok: bool, label: String) -> void:
    if not ok:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func allowed(_x: float, _z: float) -> bool:
    return true
func height(_x: float, _z: float) -> float:
    return 0.0
func cell(value: float) -> int:
    return floori(value / 64.0)
func environment(identity: String, climate: String) -> Dictionary:
    return {"state_id": identity, "regions": [{"region_id": "fixture",
        "climate_type": climate, "ecological_zone": "forest",
        "tree_suitability": 0.9, "vegetation_density": 0.9,
        "rock_exposure": 0.2, "snow_cover": 0.0}]}
func run() -> void:
    var pool = Residency.new()
    var before: Dictionary = {}
    pool.update(Vector3.ZERO, 30, 1.0, 10.0, 60.0, 85.0, 101, 1024.0, Callable(self, "allowed"))
    check(pool.records.size() == 30, "initial pool fills budget")
    before = pool.records.duplicate(true)
    var center := Vector3(12.0, 0.0, 8.0)
    pool.update(center, 30, 0.0, 10.0, 60.0, 85.0, 101, 1024.0, Callable(self, "allowed"))
    check(pool.records == before, "movement and environmental density changes preserve loaded objects")
    pool.update(center, 30, 1.0, 10.0, 60.0, 85.0, 101, 1024.0, Callable(self, "allowed"))
    check(pool.records == before, "repeated refresh cannot replace local objects")
    for step in range(1, 80):
        center = Vector3(float(step) * 5.0, 0.0, float(step) * 2.0)
        before = pool.records.duplicate(true)
        pool.update(center, 30, 1.0, 10.0, 60.0, 85.0, 101, 1024.0, Callable(self, "allowed"))
        for key in before:
            if Vector2(center.x, center.z).distance_to(before[key]["point"]) <= 85.0:
                check(pool.records.has(key) and pool.records[key] == before[key], "retained identities and positions are immutable")
        for key in pool.records:
            if not before.has(key):
                check(Vector2(center.x, center.z).distance_to(pool.records[key]["point"]) >= 45.0, "new objects only load outside protected radius")
        check(pool.records.size() <= 30, "long walk respects bounded pool")
    pool.update(Vector3(-700, 0, -700), 30, 0.0, 10.0, 60.0, 85.0, 101, 1024.0, Callable(self, "allowed"))
    check(pool.records.is_empty(), "objects beyond retention radius unload")

    var holder := Node3D.new()
    root.add_child(holder)
    var nature = Assets.new(holder, Callable(self, "height"), Callable(self, "allowed"), Callable(self, "cell"), 1024.0)
    nature.build()
    check(nature.vendor_ready(), "actual vendor assets must be available")
    nature.update_environment(environment("forest", "temperate_humid"))
    nature.rebuild(Vector3.ZERO, Vector3.FORWARD, "fixture", true)
    var originals: Dictionary = nature._residencies["tree"].records.duplicate(true)
    check(originals.size() > 0, "actual trees materialize")
    nature.update_environment(environment("mountain", "cool_montane"))
    nature.rebuild(Vector3(12, 0, 0), Vector3.BACK, "fixture", true)
    for key in originals:
        var current: Dictionary = nature._residencies["tree"].records[key]
        check(current["transform"] == originals[key]["transform"], "walking and turning preserve rendered transform")
        check(current["asset"] == originals[key]["asset"], "regional change cannot replace nearby tree species")
    # Trigger arrivals in a new climate while keeping overlapping old trees.
    nature.rebuild(Vector3(80, 0, 0), Vector3.LEFT, "fixture", true)
    for layer in nature._asset_batches:
        for identity in nature._asset_batches[layer]:
            var batch: MultiMeshInstance3D = nature._asset_batches[layer][identity]
            if layer == "plant":
                continue
            var physical = batch.get_node_or_null("PhysicalInstances")
            check(physical != null, "trees and rocks retain physical colliders")
            for i in range(batch.multimesh.visible_instance_count):
                var body: StaticBody3D = physical.get_child(i)
                check(body.transform == batch.multimesh.get_instance_transform(i), "collider matches immutable rendered object")
                check(not body.get_child(0).disabled, "visible collider remains enabled")

    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    await process_frame
    stage.set_process(false)
    var local_id := "%d:%d" % [stage._cell(stage._position.x), stage._cell(stage._position.z)]
    var local_tile: Node3D = stage._tiles[local_id]
    var local_instance_id := local_tile.get_instance_id()
    var vegetation_before: Dictionary = stage._midground_residency.records.duplicate(true)
    var sampled_height: float = stage._height(stage._position.x, stage._position.z)
    var local_ground = local_tile.get_child(0)
    var saved_heights: PackedFloat32Array = local_ground.get_meta("resident_ground_heights")
    var raised_heights := saved_heights.duplicate()
    for i in range(raised_heights.size()):
        raised_heights[i] += 7.0
    local_ground.set_meta("resident_ground_heights", raised_heights)
    check(absf(stage._height(stage._position.x, stage._position.z) - sampled_height - 7.0) < 0.001, "feet height reads resident mesh vertices rather than refreshed cognitive target")
    local_ground.set_meta("resident_ground_heights", saved_heights)
    stage._rebuild_active_tiles()
    check(absf(stage._height(stage._position.x, stage._position.z) - sampled_height) < 0.001, "nearby ground height survives refresh")
    check(stage._tiles[local_id].get_instance_id() == local_instance_id, "cognitive terrain refresh preserves nearby tile and decor")
    stage._position += Vector3(12, 0, 0)
    stage._camera_forward = -stage._camera_forward
    stage._rebuild_midground_vegetation()
    for key in vegetation_before:
        var old: Dictionary = vegetation_before[key]
        if Vector2(stage._position.x, stage._position.z).distance_to(old["point"]) <= 45.0:
            check(stage._midground_residency.records.has(key), "midground cannot disappear inside protected radius")
            check(stage._midground_residency.records[key]["transform"] == old["transform"], "midground transform remains fixed")
    holder.queue_free()
    stage.queue_free()
    await process_frame
    print("Nature residency 008CK smoke: ", failures, " failures")
    quit(1 if failures else 0)
