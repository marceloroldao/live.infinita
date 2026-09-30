extends Node2D

# A fixed draw budget, independent of persistent world size. No decorative Nodes.
const GRASS_COUNT := 74
const FOREST_TREE_COUNT := 17
const FOREST_STONE_COUNT := 19
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
    var forest: float = float(mix.get("forest", 0.0))
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
    _forest_floor(forest, night, shift)
    _forest_trees(forest, night, wind, shift)
    _river(river, night, shift)
    _village(float(mix.get("village", 0.0)), night, stage)
    # Ground cover belongs to the visible diorama, not a persistent population.
    for i in range(GRASS_COUNT):
        var x := fmod(i * 137.7, 760.0) - 20.0
        var y := 665.0 + fmod(i * 79.3, 365.0)
        if river > 0.001 and y > 742.0 + sin(x * 0.007) * 38.0 and y < 821.0 + sin(x * 0.007) * 38.0: continue
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

func _forest_floor(weight: float, night: float, shift: Vector2) -> void:
    if weight <= 0.001: return
    # A visual path in the scenery. It does not create a road, region or
    # persistent entity. The main actor continues to come from World State.
    var outer := PackedVector2Array()
    var inner := PackedVector2Array()
    for i in range(23):
        var t := float(i) / 22.0
        var y := lerpf(600.0, 1120.0, t)
        var center_x := 360.0 + sin(t * 3.8 + 0.35) * (62.0 + 27.0 * t)
        var half_width := lerpf(24.0, 152.0, t)
        outer.append(Vector2(center_x - half_width, y) + shift * 0.54)
        inner.append(Vector2(center_x - half_width * 0.78, y) + shift * 0.54)
    for i in range(22, -1, -1):
        var t := float(i) / 22.0
        var y := lerpf(600.0, 1120.0, t)
        var center_x := 360.0 + sin(t * 3.8 + 0.35) * (62.0 + 27.0 * t)
        var half_width := lerpf(24.0, 152.0, t)
        outer.append(Vector2(center_x + half_width, y) + shift * 0.54)
        inner.append(Vector2(center_x + half_width * 0.78, y) + shift * 0.54)
    var border := Color("#4e6446").lerp(Color("#253a35"), night)
    border.a = weight * 0.88
    var earth := Color("#88765c").lerp(Color("#39413b"), night)
    earth.a = weight * 0.79
    draw_colored_polygon(outer, border)
    draw_colored_polygon(inner, earth)
    # Pebbles are positions derived from a stable index, never random per frame.
    for i in range(FOREST_STONE_COUNT):
        var t := (float(i) + 0.5) / float(FOREST_STONE_COUNT)
        var y := lerpf(626.0, 1083.0, t)
        var center_x := 360.0 + sin(t * 3.8 + 0.35) * (62.0 + 27.0 * t)
        var x := center_x + sin(float(i) * 14.27) * lerpf(9.0, 91.0, t)
        var pos := Vector2(x, y) + shift * 0.54
        var stone := Color("#a29979").lerp(Color("#53605b"), night)
        stone.a = weight * 0.45
        draw_set_transform(pos, 0.0, Vector2(1.5 + t, 0.42))
        draw_circle(Vector2.ZERO, 2.0 + float(i % 3), stone)
    draw_set_transform(Vector2.ZERO)


func _forest_trees(weight: float, night: float, wind: float, shift: Vector2) -> void:
    if weight <= 0.001: return
    # Bounded decor behind materialized entities, with a clear central path.
    # No tree is inserted in the World State, and no mesh is loaded per frame.
    var bark := Color("#433f32").lerp(Color("#283335"), night)
    bark.a = weight
    var canopy := Color("#335b42").lerp(Color("#203a3b"), night)
    canopy.a = weight
    var crown := Color("#51774c").lerp(Color("#304d46"), night)
    crown.a = weight * 0.93
    for i in range(FOREST_TREE_COUNT):
        var left := i % 2 == 0
        var side := -1.0 if left else 1.0
        var row := float(i / 2)
        var depth := row / 8.0
        var x := 360.0 + side * (lerpf(105.0, 355.0, depth) + sin(float(i) * 6.27) * 25.0)
        var y := 605.0 + depth * 355.0 + cos(float(i) * 2.7) * 15.0
        var scale_value := lerpf(0.45, 1.18, depth)
        var origin := Vector2(x, y) + shift * (0.26 + depth * 0.30)
        var h := 72.0 * scale_value
        var sway := sin(visual_time * 0.66 + float(i) * 1.4) * (0.7 + wind * 3.0)
        draw_line(origin, origin + Vector2(0, -h), bark, 5.5 * scale_value, true)
        draw_line(origin + Vector2(0, -h * 0.55), origin + Vector2(side * 17, -h * 0.76), bark, 2.2 * scale_value, true)
        var crown_pos := origin + Vector2(sway, -h)
        for lobe in range(3):
            var offset := Vector2(float(lobe - 1) * 13.0 * scale_value, float(lobe % 2) * 8.0 * scale_value)
            draw_circle(crown_pos + offset, (25.0 + float((i + lobe) % 3) * 4.0) * scale_value, canopy)
        draw_circle(crown_pos + Vector2(-6, -5) * scale_value, 19.0 * scale_value, crown)
    # Ferns and fallen leaves, drawn only in the vegetation band.
    for i in range(25):
        var side := -1.0 if i % 2 == 0 else 1.0
        var y := 705.0 + float((i * 71) % 303)
        var x := 360.0 + side * (120.0 + float((i * 43) % 240))
        var p := Vector2(x, y) + shift * 0.55
        var leaf := Color("#7e995b").lerp(Color("#425b49"), night)
        leaf.a = weight * 0.76
        var wobble := sin(visual_time * 0.95 + i) * (1.0 + wind * 3.0)
        for blade in range(3):
            draw_line(p, p + Vector2((float(blade) - 1.0) * 8.0 + wobble, -8.0 - float((i + blade) % 4) * 4.0), leaf, 2.0, true)


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

