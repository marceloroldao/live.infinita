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

func _normalized_biome(value: String) -> String:
    var biome := value.strip_edges().to_lower()
    match biome:
        "floresta", "woodland": return "forest"
        "campo", "grassland", "meadow": return "field"
        "rio", "riverbank", "water": return "river"
        "aldeia", "village", "town": return "village"
        _: return biome if not biome.is_empty() else "forest"

func _transition(environment: Dictionary) -> Dictionary:
    var value = environment.get("transition", {})
    if typeof(value) != TYPE_DICTIONARY:
        return {}
    return value

func _biome_mix(environment: Dictionary) -> Dictionary:
    var current := _normalized_biome(str(environment.get("biome", "forest")))
    var transition := _transition(environment)
    var next := _normalized_biome(str(transition.get("to_biome", current)))
    var progress := clamp(float(transition.get("progress", 0.0)), 0.0, 1.0)
    if next == current or transition.is_empty():
        return {current: 1.0}
    return {current: 1.0 - progress, next: progress}

func _draw_forest_mist(intensity: float, weight: float) -> void:
    if weight <= 0.001: return
    var amount := int(5 + 5 * intensity)
    for i in range(amount):
        var phase := visual_time * (4.0 + float(i % 3)) + float(i * 71)
        var x := STAGE.position.x - 160.0 + fmod(float(i * 137) + phase, STAGE.size.x + 320.0)
        var y := STAGE.position.y + STAGE.size.y * (0.56 + 0.055 * float(i % 5))
        var width := 145.0 + float((i * 29) % 90)
        var alpha := (0.025 + 0.035 * intensity) * weight
        draw_set_transform(Vector2(x, y), 0.0, Vector2(1.0, 0.28))
        draw_circle(Vector2.ZERO, width, Color(0.82, 0.91, 0.88, alpha))
        draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

func _draw_forest_motes(intensity: float, weight: float) -> void:
    if weight <= 0.001: return
    var amount := int(10 + 10 * intensity)
    for i in range(amount):
        var speed := 7.0 + float(i % 5) * 1.8
        var x := STAGE.position.x + fmod(float(i * 97) + visual_time * speed, STAGE.size.x)
        var drift := sin(visual_time * 0.9 + float(i) * 1.7) * 18.0
        var y := STAGE.position.y + 90.0 + fmod(float(i * 83) + visual_time * (3.0 + float(i % 3)), STAGE.size.y - 180.0) + drift
        var radius := 1.0 + float(i % 3) * 0.45
        draw_circle(Vector2(x, y), radius, Color(0.90, 0.94, 0.63, (0.10 + 0.10 * intensity) * weight))

func _draw_field_air(intensity: float, weight: float) -> void:
    if weight <= 0.001: return
    var amount := int(8 + 10 * intensity)
    for i in range(amount):
        var speed := 10.0 + float(i % 4) * 2.5
        var x := STAGE.position.x + fmod(float(i * 113) + visual_time * speed, STAGE.size.x)
        var y := STAGE.position.y + STAGE.size.y * 0.58 + fmod(float(i * 61), STAGE.size.y * 0.30)
        var wobble := sin(visual_time * 1.1 + float(i) * 0.7) * 7.0
        draw_line(Vector2(x - 8.0, y + wobble), Vector2(x + 8.0, y + wobble - 2.0), Color(0.78, 0.86, 0.57, (0.05 + 0.09 * intensity) * weight), 1.0)

func _draw_river_shimmer(intensity: float, weight: float) -> void:
    if weight <= 0.001: return
    var y0 := STAGE.position.y + STAGE.size.y * 0.70
    draw_rect(Rect2(STAGE.position.x, y0, STAGE.size.x, STAGE.size.y * 0.16), Color(0.20, 0.48, 0.60, (0.04 + 0.08 * intensity) * weight))
    for i in range(12):
        var x := STAGE.position.x + fmod(float(i * 79) + visual_time * (11.0 + float(i % 3) * 4.0), STAGE.size.x)
        var y := y0 + 10.0 + float(i % 5) * 18.0
        var width := 18.0 + float((i * 11) % 26)
        draw_line(Vector2(x, y), Vector2(min(STAGE.end.x, x + width), y), Color(0.78, 0.94, 0.98, (0.08 + 0.13 * intensity) * weight), 1.3)

func _draw_village_glow(intensity: float, weight: float) -> void:
    if weight <= 0.001: return
    for i in range(5):
        var x := STAGE.position.x + 85.0 + float(i) * 112.0
        var y := STAGE.position.y + STAGE.size.y * 0.64 + float(i % 2) * 24.0
        var pulse := 0.85 + 0.15 * sin(visual_time * 1.3 + float(i))
        draw_circle(Vector2(x, y), 26.0, Color(1.0, 0.60, 0.24, (0.018 + 0.025 * intensity) * weight * pulse))
        draw_circle(Vector2(x, y), 4.0, Color(1.0, 0.78, 0.42, (0.16 + 0.18 * intensity) * weight * pulse))

func _draw_biome(biome: String, intensity: float, weight: float) -> void:
    match biome:
        "forest":
            _draw_forest_mist(intensity, weight)
            _draw_forest_motes(intensity, weight)
        "field": _draw_field_air(intensity, weight)
        "river": _draw_river_shimmer(intensity, weight)
        "village": _draw_village_glow(intensity, weight)
        _:
            pass

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
    var weather := str(environment.get("weather", "clear")).to_lower()
    var intensity := clamp(float(environment.get("atmosphere_intensity", 0.55)), 0.0, 1.0)

    var mix := _biome_mix(environment)
    for biome in mix.keys():
        _draw_biome(str(biome), intensity, float(mix[biome]))

    match weather:
        "rain", "chuva": _draw_rain(intensity)
        "dust", "dry", "poeira", "seco": _draw_dust(intensity)
        _:
            pass
