extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func project_flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("z", 0.0)))

func sample_height(x: float, z: float) -> float:
    return sin(x * 0.01) + cos(z * 0.01)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var terrain_script = load("res://world_map_cognitive_terrain.gd")
    var host := Node3D.new()
    root.add_child(host)
    var terrain = terrain_script.new(host)

    var projection := {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "smoke-batched-trails-008ad",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [],
        "transitions": [],
        "spatial_trails": [
            {
                "from_position": {"x": 0.0, "z": 0.0},
                "to_position": {"x": 64.0, "z": 0.0},
                "count": 8,
                "trail_strength": 0.9,
                "trail_candidate": true,
                "trail_width_m": 1.2,
            },
            {
                "from_position": {"x": 10.0, "z": 20.0},
                "to_position": {"x": 90.0, "z": 65.0},
                "count": 5,
                "trail_strength": 0.7,
                "trail_candidate": true,
                "trail_width_m": 0.9,
            },
            {
                "from_position": {"x": -20.0, "z": 40.0},
                "to_position": {"x": 50.0, "z": 100.0},
                "count": 3,
                "trail_strength": 0.5,
                "trail_candidate": true,
                "trail_width_m": 0.7,
            },
        ],
    }

    var changed: bool = terrain.update(
        projection,
        Callable(self, "project_flat"),
        Callable(self, "sample_height"),
    )
    check(changed, "Projection should update")
    check(terrain.trail_count() == 3, "All candidate trails must remain counted")

    var batches := 0
    var legacy_segments := 0
    var vertex_count := 0
    for child in terrain._root.get_children():
        var name := str(child.name)
        if name == "MemoryTrailBatch":
            batches += 1
            if child is MeshInstance3D and child.mesh != null:
                var arrays = child.mesh.surface_get_arrays(0)
                if arrays.size() > Mesh.ARRAY_VERTEX:
                    var vertices = arrays[Mesh.ARRAY_VERTEX]
                    vertex_count = vertices.size()
        elif name.begins_with("MemoryTrail_"):
            legacy_segments += 1

    check(batches == 1, "Trails must use one batched mesh")
    check(legacy_segments == 0, "Legacy per-segment trail nodes must be absent")
    check(vertex_count >= 18, "Batched trail mesh must contain geometry")

    host.queue_free()
    await process_frame
    print("Batched cognitive trails smoke: ", failures, " failures")
    quit(1 if failures else 0)
