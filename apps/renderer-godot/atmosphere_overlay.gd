extends Node2D

const STAGE := Rect2(42.0, 250.0, 636.0, 760.0)

var visual_time := 0.0

func _process(delta: float) -> void:
    visual_time += delta
    queue_redraw()

func _environment() -> Dictionary:
    var parent = get_parent()
    if parent == null:
        return {}
    var value = parent.get("world")
    if typeof(value) != TYPE_DICTIONARY:
        return {}
    var environment = value.get("environment", {})
    return environment if typeof(environment) == TYPE_DICTIONARY else {}

func _draw_forest_mist(intensity: float) -> void:
    var amount := int(5 + 5 * intensity)
    for i in range(amount):
        var phase := visual_time * (4.0 + float(i % 3)) + float(i * 71)
        var x := STAGE.position.x - 160.0 + fmod(float(i * 137) + phase, STAGE.size.x + 320.0)
        var y := STAGE.position.y + STAGE.size.y * (0.56 + 0.055 * float(i % 5))
        var width := 145.0 + float((i * 29) % 90)
        var alpha := 0.025 + 0.035 * intensity
        draw_set_transform(Vector2(x, y), 0.0, Vector2(1.0, 0.28))
        draw_circle(Vector2.ZERO, width, Color(0.82, 0.91, 0.88, alpha))
        draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

func _draw_forest_motes(intensity: float) -> void:
    var amount := int(10 + 10 * intensity)
    for i in range(amount):
        var speed := 7.0 + float(i % 5) * 1.8
        var x := STAGE.position.x + fmod(float(i * 97) + visual_time * speed, STAGE.size.x)
        var drift := sin(visual_time * 0.9 + float(i) * 1.7) * 18.0
        var y := STAGE.position.y + 90.0 + fmod(float(i * 83) + visual_time * (3.0 + float(i % 3)), STAGE.size.y - 180.0) + drift
        var radius := 1.0 + float(i % 3) * 0.45
        draw_circle(Vector2(x, y), radius, Color(0.90, 0.94, 0.63, 0.10 + 0.10 * intensity))

func _draw_rain(intensity: float) -> void:
    var amount := int(24 + 40 * intensity)
    for i in range(amount):
        var speed := 310.0 + float(i % 7) * 27.0
        var x := STAGE.position.x + fmod(float(i * 53) + visual_time * 48.0, STAGE.size.x)
        var y := STAGE.position.y + fmod(float(i * 101) + visual_time * speed, STAGE.size.y)
        var length := 12.0 + float(i % 4) * 3.0
        draw_line(Vector2(x, y), Vector2(x - 4.0, y + length), Color(0.72, 0.85, 0.96, 0.17 + 0.18 * intensity), 1.2)
    draw_rect(STAGE, Color(0.14, 0.22, 0.30, 0.05 + 0.05 * intensity))

func _draw_dust(intensity: float) -> void:
    var amount := int(10 + 18 * intensity)
    for i in range(amount):
        var speed := 14.0 + float(i % 5) * 4.0
        var x := STAGE.position.x + fmod(float(i * 79) + visual_time * speed, STAGE.size.x)
        var y := STAGE.position.y + STAGE.size.y * 0.55 + fmod(float(i * 47), STAGE.size.y * 0.38)
        var wobble := sin(visual_time * 1.2 + float(i)) * 11.0
        var radius := 1.5 + float(i % 4) * 0.8
        draw_circle(Vector2(x, y + wobble), radius, Color(0.88, 0.72, 0.45, 0.08 + 0.10 * intensity))

func _draw() -> void:
    var environment := _environment()
    var biome := str(environment.get("biome", "forest")).to_lower()
    var weather := str(environment.get("weather", "clear")).to_lower()
    var intensity := clamp(float(environment.get("atmosphere_intensity", 0.55)), 0.0, 1.0)

    if biome in ["forest", "floresta", "woodland"]:
        _draw_forest_mist(intensity)
        _draw_forest_motes(intensity)

    match weather:
        "rain", "chuva":
            _draw_rain(intensity)
        "dust", "dry", "poeira", "seco":
            _draw_dust(intensity)
        _:
            pass
