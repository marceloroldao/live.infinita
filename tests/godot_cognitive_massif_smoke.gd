extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func project_flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("z", 0.0)))

func sample_height(_x: float, _z: float) -> float:
    return 2.0

func count_static_bodies(node: Node) -> int:
    var total := 1 if node is StaticBody3D else 0
    for child in node.get_children():
        total += count_static_bodies(child)
    return total

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var terrain_script = load("res://world_map_cognitive_terrain.gd")
    var host := Node3D.new()
    root.add_child(host)
    var terrain = terrain_script.new(host)

    var projection := {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "smoke-massif-008ac",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "strong",
                "center": {"x": 40.0, "z": 20.0},
                "elevation_bias_m": 16.0,
                "influence_radius_m": 180.0,
                "cognitive_mass": 0.92,
                "terrain_role": "uplift",
                "lake_candidate": false,
            },
            {
                "region_id": "weak",
                "center": {"x": -50.0, "z": 10.0},
                "elevation_bias_m": 4.0,
                "influence_radius_m": 150.0,
                "cognitive_mass": 0.80,
                "terrain_role": "uplift",
                "lake_candidate": false,
            },
            {
                "region_id": "lake",
                "center": {"x": 0.0, "z": -60.0},
                "elevation_bias_m": -9.0,
                "influence_radius_m": 120.0,
                "cognitive_mass": 0.75,
                "terrain_role": "basin",
                "lake_candidate": true,
            },
        ],
        "transitions": [],
        "spatial_trails": [],
    }

    var changed: bool = terrain.update(
        projection,
        Callable(self, "project_flat"),
        Callable(self, "sample_height"),
    )
    check(changed, "Projection should update")
    check(terrain.massif_count() == 1, "Only strong uplift should become massif")
    check(terrain.lake_count() == 1, "Lake projection must remain intact")

    var massif_meshes := 0
    var max_height := 0.0
    for child in terrain._root.get_children():
        if str(child.name).begins_with("MemoryMassif_"):
            massif_meshes += 1
            if child is MeshInstance3D and child.mesh is CylinderMesh:
                max_height = maxf(max_height, float(child.mesh.height))
    check(massif_meshes == 3, "One massif must use three low-poly peaks")
    check(max_height <= 68.0, "Visual massif height must remain bounded")
    check(max_height >= 50.0, "Strong uplift should be visually prominent")
    check(count_static_bodies(terrain._root) == 0, "Massifs must not add collision")

    host.queue_free()
    await process_frame
    print("Cognitive massif smoke: ", failures, " failures")
    quit(1 if failures else 0)
