extends Node2D

# A fixed draw budget, independent of persistent world size. No decorative Nodes.
const GRASS_COUNT := 74
var visual_time := 0.0

func _process(delta: float) -> void:
    visual_time += delta
    queue_redraw()

func _draw() -> void:
    var stage = get_parent()
    var night: float = stage.night_amount
    var wind: float = stage.wind_amount
    var mix: Dictionary = stage.get_node("AtmosphereOverlay")._biome_mix(stage.world.get("environment", {}))
    var field: float = float(mix.get("field", 0.0))
    var river: float = float(mix.get("river", 0.0))
    var shift: Vector2 = stage.camera_offset
    var far := Color("#769b8e").lerp(Color("#24334f"), night)
    var middle := Color("#527e67").lerp(Color("#1b3340"), night)
    var ground := Color("#476d46").lerp(Color("#192f30"), night)
    # Smooth sampled contours, with subdued parallax anchored to the director.
    for layer in range(3):
        var points := PackedVector2Array()
        for i in range(39):
            var x := -40.0 + i * 22.0
            var y := 478.0 + layer * 77.0 + sin(x * 0.006 + layer * 1.7) * (46.0 - field * 22.0) + cos(x * 0.012) * 13.0
            points.append(Vector2(x, y) + shift * (0.12 + layer * 0.12))
        points.append(Vector2(800, 1280))
        points.append(Vector2(-80, 1280))
        draw_colored_polygon(points, far if layer == 0 else (middle if layer == 1 else ground))
    # Distant woods fade out into the open field. Only silhouettes, never entities.
    for i in range(27):
        var x := i * 30.0 - 30.0
        var y := 566.0 + sin(x * 0.006 + 1.7) * 35.0
        var height := 25.0 + float((i * 19) % 33)
        var color := middle.darkened(0.09)
        color.a = 0.7 * (1.0 - field)
        var base := Vector2(x, y) + shift * 0.25
        draw_colored_polygon(PackedVector2Array([base + Vector2(-13, 0), base + Vector2(0, -height), base + Vector2(14, 0)]), color)
    _river(river, night, shift)
    _village(float(mix.get("village", 0.0)), night, stage)
    # Ground cover belongs to the visible diorama, not a persistent population.
    for i in range(GRASS_COUNT):
        var x := fmod(i * 137.7, 760.0) - 20.0
        var y := 665.0 + fmod(i * 79.3, 365.0)
        var p := Vector2(x, y) + shift * 0.65
        var h := 5.0 + float(i % 5) * 2.0 + field * 4.0
        var sway := sin(visual_time * 1.15 + x * 0.022) * (1.0 + wind * 4.0)
        var tint := Color("#8fa268").lerp(Color("#355447"), night)
        for blade in range(3):
            var tip := p + Vector2((blade - 1) * 4.0 + sway, -h + abs(blade - 1) * 2)
            draw_line(p, tip, tint, 1.4, true)
        if i % 9 == 0:
            draw_circle(p + Vector2(sway, -h), 2.5, Color("#e5c487").lerp(Color("#6d777c"), night))
        if i % 13 == 0:
            draw_set_transform(p + Vector2(12, 3), -0.2, Vector2(1.6, 0.7))
            draw_circle(Vector2.ZERO, 5.0, Color("#7a8572").lerp(Color("#38464a"), night))
            draw_set_transform(Vector2.ZERO)

func _river(weight: float, night: float, shift: Vector2) -> void:
    if weight < 0.001: return
    var bank := PackedVector2Array()
    var water := PackedVector2Array()
    for i in range(31):
        var x := -40.0 + i * 27.0
        var y := 744.0 + sin(x * 0.007) * 38.0
        bank.append(Vector2(x, y - 10.0) + shift * 0.5)
        water.append(Vector2(x, y) + shift * 0.5)
    for i in range(30, -1, -1):
        var x := -40.0 + i * 27.0
        var y := 819.0 + sin(x * 0.007) * 38.0
        bank.append(Vector2(x, y + 10.0) + shift * 0.5)
        water.append(Vector2(x, y) + shift * 0.5)
    var sand := Color("#a3a27c").lerp(Color("#394a47"), night)
    sand.a = weight
    var blue := Color("#4f9298").lerp(Color("#24465b"), night)
    blue.a = weight
    draw_colored_polygon(bank, sand)
    draw_colored_polygon(water, blue)
    for i in range(25):
        var x := fmod(i * 93.0 + visual_time * (7.0 + i % 3), 810.0) - 45.0
        var y := 756.0 + sin(x * 0.007) * 38.0 + (i % 5) * 11.0
        var alpha := (0.18 + 0.10 * sin(visual_time * 0.7 + i)) * weight
        var p := Vector2(x, y) + shift * 0.5
        draw_line(p, p + Vector2(18.0 + i % 17, 0), Color(0.8, 0.94, 0.88, alpha), 1.5, true)
    for i in range(12):
        var x := float(i) * 67.0
        var y := 831.0 + sin(x * 0.007) * 38.0
        draw_set_transform(Vector2(x, y) + shift * 0.5, 0.1, Vector2(1.5, 0.6))
        draw_circle(Vector2.ZERO, 7.0 + i % 4, Color(0.43, 0.49, 0.43, weight))
        draw_set_transform(Vector2.ZERO)

func _village(weight: float, night: float, stage: Node2D) -> void:
    if weight < 0.001: return
    # A village motif is anchored to at most two materialized gathering points.
    # These silhouettes are scenery, with no entity identity or simulation state.
    var count := 0
    for visual in stage.entity_nodes.values():
        if visual.entity_type != "campfire": continue
        count += 1
        if count > 2: break
        var anchor: Vector2 = visual.position + stage.camera_offset
        for side in [-1, 1]:
            var p := Vector2(clampf(anchor.x + side * 205, 72, 648), anchor.y - 18)
            var wall := Color("#b3a980").lerp(Color("#586b70"), night)
            wall.a = weight * visual.modulate.a
            var roof := Color("#796153").lerp(Color("#354251"), night)
            roof.a = wall.a
            draw_rect(Rect2(p + Vector2(-33, -35), Vector2(66, 51)), wall)
            draw_colored_polygon(PackedVector2Array([p + Vector2(-41, -32), p + Vector2(-4, -68), p + Vector2(41, -32)]), roof)
            draw_rect(Rect2(p + Vector2(-5, -11), Vector2(13, 27)), roof)
            var window := Color("#a4b8a0").lerp(Color("#efca7c"), night)
            window.a = wall.a
            draw_rect(Rect2(p + Vector2(-24, -22), Vector2(10, 14)), window)
            for j in range(4):
                var progress := float(j) / 4.0
                var path := p.lerp(anchor + Vector2(0, 24), progress)
                draw_set_transform(path, 0, Vector2(1.4, 0.45))
                draw_circle(Vector2.ZERO, 7, Color(0.70, 0.65, 0.48, 0.4 * wall.a))
            draw_set_transform(Vector2.ZERO)
            if side == 1:
                for puff in range(3):
                    var phase := fmod(visual_time * 0.085 + puff * 0.33, 1.0)
                    var pos := p + Vector2(18 + sin(phase * 4 + visual_time * 0.3) * 10, -57 - phase * 55)
                    draw_circle(pos, 4 + phase * 8, Color(0.79, 0.84, 0.79, (1.0 - phase) * wall.a * 0.11))
