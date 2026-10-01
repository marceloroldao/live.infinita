extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var terrain_script = load("res://world_map_cognitive_terrain.gd")
    var host := Node3D.new()
    root.add_child(host)
    var terrain = terrain_script.new(host)

    var a := Vector2(0.0, 0.0)
    var b := Vector2(64.0, 0.0)
    terrain._spatial_trails = [{
        "a": a,
        "b": b,
        "count": 10,
        "trail_strength": 0.8,
        "trail_candidate": true,
        "trail_width": 1.0,
    }]

    var center: Vector2 = terrain._natural_trail_point(a, b, 0.5, 10, 0.8)
    var corridor: Dictionary = terrain.decor_profile_at(center.x, center.y)
    check(not bool(corridor.get("allow_decor", true)), "Trail center must clear decoration")
    check(str(corridor.get("role", "")) == "trail_corridor", "Trail center role")

    var edge_point := center + Vector2(0.0, 3.0)
    var edge: Dictionary = terrain.decor_profile_at(edge_point.x, edge_point.y)
    check(bool(edge.get("allow_decor", false)), "Trail edge keeps low decoration")
    check(str(edge.get("role", "")) == "trail_edge", "Trail edge role")
    check(float(edge.get("influence", 0.0)) > 0.0, "Trail edge influence")

    var surface: Dictionary = terrain.surface_at(center.x, center.y)
    check(bool(surface.get("walkable", false)), "Visual trail must not change traversability")
    check(str(surface.get("surface", "")) == "terrain", "Visual trail surface stays terrain")

    var far: Dictionary = terrain.decor_profile_at(center.x, center.y + 12.0)
    check(bool(far.get("allow_decor", false)), "Far vegetation remains allowed")
    check(str(far.get("role", "")) != "trail_corridor", "Far point outside corridor")

    host.queue_free()
    await process_frame
    print("Memory trail corridor smoke: ", failures, " failures")
    quit(1 if failures else 0)
