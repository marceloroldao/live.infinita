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
    var p0: Vector2 = terrain._natural_trail_point(a, b, 0.0, 2, 0.2)
    var p1: Vector2 = terrain._natural_trail_point(a, b, 1.0, 2, 0.2)
    check(p0.distance_to(a) < 0.0001, "Natural trail must preserve start")
    check(p1.distance_to(b) < 0.0001, "Natural trail must preserve end")

    var midpoint: Vector2 = terrain._natural_trail_point(a, b, 0.5, 2, 0.2)
    check(absf(midpoint.y) > 0.2, "Weak/recent trail should visibly meander")
    check(absf(midpoint.y) <= 4.5, "Meander must remain bounded")

    var reverse_mid: Vector2 = terrain._natural_trail_point(b, a, 0.5, 2, 0.2)
    check(midpoint.distance_to(reverse_mid) < 0.0001, "Reverse direction must share geometry")

    var quarter: Vector2 = terrain._natural_trail_point(a, b, 0.25, 2, 0.2)
    var reverse_quarter: Vector2 = terrain._natural_trail_point(b, a, 0.75, 2, 0.2)
    check(quarter.distance_to(reverse_quarter) < 0.0001, "S-curve must be direction invariant")

    var strong_mid: Vector2 = terrain._natural_trail_point(a, b, 0.5, 12, 1.0)
    check(absf(strong_mid.y) < absf(midpoint.y), "Repeated strong trail should straighten")

    var same_a := Vector2(5.0, 5.0)
    var same: Vector2 = terrain._natural_trail_point(same_a, same_a, 0.5, 4, 0.8)
    check(same.distance_to(same_a) < 0.0001, "Degenerate trail must remain stable")

    host.queue_free()
    await process_frame
    print("Cognitive trail naturalization smoke: ", failures, " failures")
    quit(1 if failures else 0)
