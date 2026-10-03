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

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var script = load("res://world_map_perceptual_assets.gd")
    check(script != null, "Perceptual assets module must load")
    if script == null:
        quit(1)
        return

    var host := Node3D.new()
    root.add_child(host)
    var hero = script.new(
        host,
        Callable(self, "height"),
        Callable(self, "allowed"),
        Callable(self, "cell"),
        1024.0,
    )

    var origin := Vector3.ZERO
    var forward := Vector3(0.0, 0.0, -1.0)

    check(
        hero._inside_corridor(origin, forward, Vector2(0.0, -12.0), 3.8),
        "Point centered in front must be inside tree/rock corridor"
    )
    check(
        hero._inside_corridor(origin, forward, Vector2(1.5, -15.0), 1.9),
        "Close lateral point must be inside understory corridor"
    )
    check(
        not hero._inside_corridor(origin, forward, Vector2(5.0, -12.0), 3.8),
        "Side point must remain available for hero assets"
    )
    check(
        not hero._inside_corridor(origin, forward, Vector2(0.0, 8.0), 3.8),
        "Point behind NOV must not be blocked by forward corridor"
    )
    check(
        not hero._inside_corridor(origin, forward, Vector2(0.0, -34.0), 3.8),
        "Far point beyond corridor length must remain available"
    )

    host.queue_free()
    await process_frame
    print("Perceptual corridor smoke: ", failures, " failures")
    quit(1 if failures else 0)
