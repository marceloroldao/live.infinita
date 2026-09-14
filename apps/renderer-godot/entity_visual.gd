extends Node2D

const LOGICAL_WORLD_SIZE := Vector2(1280.0, 720.0)
const PORTRAIT_STAGE := Rect2(90.0, 330.0, 540.0, 620.0)

var entity_id: String = ""
var entity_type: String = ""
var entity_data: Dictionary = {}
var data_signature: String = ""
var world_position := Vector2.ZERO
var target_position := Vector2.ZERO
var target_presentation_scale := 1.0
var visual_time := 0.0

func world_to_portrait(value: Vector2) -> Vector2:
    var nx: float = clampf(value.x / LOGICAL_WORLD_SIZE.x, 0.0, 1.0)
    var ny: float = clampf(value.y / LOGICAL_WORLD_SIZE.y, 0.0, 1.0)
    return Vector2(
        PORTRAIT_STAGE.position.x + nx * PORTRAIT_STAGE.size.x,
        PORTRAIT_STAGE.position.y + ny * PORTRAIT_STAGE.size.y
    )

func apply_entity(next_entity: Dictionary) -> bool:
    var next_signature := JSON.stringify(next_entity)
    if next_signature == data_signature:
        return false

    entity_data = next_entity.duplicate(true)
    entity_id = str(entity_data.get("id", ""))
    entity_type = str(entity_data.get("type", ""))
    data_signature = next_signature

    var p_data = entity_data.get("position", {})
    world_position = Vector2(float(p_data.get("x", 0)), float(p_data.get("y", 0)))
    target_position = world_to_portrait(world_position)
    if position == Vector2.ZERO:
        position = target_position
    queue_redraw()
    return true

func set_presentation_target(screen_position: Vector2, emphasis: float = 1.0) -> void:
    target_position = screen_position
    target_presentation_scale = clampf(emphasis, 0.75, 1.35)

func restore_default_presentation(emphasis: float = 1.0) -> void:
    set_presentation_target(world_to_portrait(world_position), emphasis)

func _process(delta: float) -> void:
    visual_time += delta
    position = position.lerp(target_position, minf(1.0, delta * 3.8))
    var uniform: float = scale.x
    uniform = lerpf(uniform, target_presentation_scale, minf(1.0, delta * 3.2))
    scale = Vector2.ONE * uniform
    if entity_type == "tree" or entity_type == "campfire":
        queue_redraw()

func _shadow(radius_x: float, radius_y: float, offset_y: float = 44.0) -> void:
    draw_set_transform(Vector2(0, offset_y), 0.0, Vector2(1.0, 0.45))
    draw_circle(Vector2.ZERO, radius_x, Color(0.02, 0.04, 0.04, 0.24))
    draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

func _draw_tree(s: float) -> void:
    _shadow(48.0 * s, 18.0 * s, 78.0 * s)
    draw_polygon(PackedVector2Array([
        Vector2(-15, 72) * s, Vector2(-10, -4) * s,
        Vector2(11, -4) * s, Vector2(18, 72) * s
    ]), PackedColorArray([Color("#4b2d20"), Color("#68402a"), Color("#74492e"), Color("#4b2d20")]))
    draw_line(Vector2(-4, 4) * s, Vector2(-6, 60) * s, Color(0.82, 0.58, 0.38, 0.22), 3.0 * s)

    var sway := sin(visual_time * 0.8 + float(abs(entity_id.hash()) % 17)) * 4.0 * s
    var dark := Color("#173d30")
    var mid := Color("#255b3d")
    var light := Color("#3d7750")
    draw_circle((Vector2(-31, -23) * s) + Vector2(sway * 0.55, 0), 39 * s, dark)
    draw_circle((Vector2(30, -21) * s) + Vector2(sway * 0.75, 0), 42 * s, dark)
    draw_circle((Vector2(0, -50) * s) + Vector2(sway, 0), 48 * s, mid)
    draw_circle((Vector2(-42, -4) * s) + Vector2(sway * 0.45, 0), 31 * s, mid)
    draw_circle((Vector2(42, -2) * s) + Vector2(sway * 0.60, 0), 32 * s, mid)
    draw_circle((Vector2(-13, -61) * s) + Vector2(sway * 1.12, 0), 28 * s, light)
    draw_circle((Vector2(17, -43) * s) + Vector2(sway * 0.92, 0), 25 * s, Color(0.30, 0.52, 0.32, 0.72))

func _draw_smoke_and_embers(s: float) -> void:
    for i in range(5):
        var phase := fmod(visual_time * (0.18 + i * 0.015) + float(i) * 0.19, 1.0)
        var rise := phase * 118.0
        var drift := sin(visual_time * 0.65 + i * 1.7) * (8.0 + rise * 0.09)
        var alpha := (1.0 - phase) * 0.16
        var radius := (10.0 + phase * 20.0) * s
        draw_circle(Vector2(drift, -58.0 - rise) * s, radius, Color(0.78, 0.80, 0.78, alpha))
    for i in range(7):
        var phase := fmod(visual_time * (0.55 + i * 0.025) + float(i) * 0.13, 1.0)
        var ex := sin(visual_time * 2.2 + i * 2.1) * (10.0 + phase * 18.0)
        var ey := -32.0 - phase * 72.0
        var alpha := (1.0 - phase) * 0.75
        draw_circle(Vector2(ex, ey) * s, (1.4 + float(i % 3) * 0.5) * s, Color(1.0, 0.58, 0.16, alpha))

func _draw_fire(s: float) -> void:
    _shadow(40.0 * s, 15.0 * s, 25.0 * s)
    draw_line(Vector2(-27, 17) * s, Vector2(26, -10) * s, Color("#5a3a28"), 10 * s)
    draw_line(Vector2(-26, -10) * s, Vector2(27, 17) * s, Color("#73503a"), 10 * s)
    var lit := bool(entity_data.get("properties", {}).get("lit", false))
    if not lit:
        draw_circle(Vector2.ZERO, 4 * s, Color(0.12, 0.10, 0.09, 0.7))
        return

    _draw_smoke_and_embers(s)
    var pulse := 1.0 + sin(visual_time * 8.0) * 0.06
    var flicker := sin(visual_time * 13.0) * 4.0
    draw_circle(Vector2(0, -18) * s, 66 * s * pulse, Color(1.0, 0.45, 0.12, 0.075))
    draw_circle(Vector2(0, -18) * s, 45 * s * pulse, Color(1.0, 0.56, 0.16, 0.11))
    var outer := PackedVector2Array([
        Vector2(-27, 8), Vector2(-19, -22), Vector2(-7, -39),
        Vector2(0, -72 + flicker), Vector2(12, -43), Vector2(28, -17), Vector2(24, 9)
    ])
    for i in range(outer.size()): outer[i] *= s
    draw_colored_polygon(outer, Color("#f0642c"))
    var inner := PackedVector2Array([
        Vector2(-13, 7), Vector2(-8, -17), Vector2(2, -43 - flicker * 0.3),
        Vector2(13, -18), Vector2(13, 7)
    ])
    for i in range(inner.size()): inner[i] *= s
    draw_colored_polygon(inner, Color("#ffd05b"))
    draw_circle(Vector2(2, -4) * s, 9 * s, Color("#fff3b0"))

func _draw_human(s: float) -> void:
    _shadow(28.0 * s, 10.0 * s, 46.0 * s)
    var skin := Color("#e8b98e")
    var coat := Color("#435a83")
    var coat_dark := Color("#2d3f62")
    draw_line(Vector2(-6, 15) * s, Vector2(-16, 49) * s, Color("#26334b"), 9 * s)
    draw_line(Vector2(6, 15) * s, Vector2(16, 49) * s, Color("#26334b"), 9 * s)
    draw_colored_polygon(PackedVector2Array([
        Vector2(-17, -23) * s, Vector2(16, -23) * s,
        Vector2(13, 22) * s, Vector2(-13, 22) * s
    ]), coat)
    draw_line(Vector2(-13, -15) * s, Vector2(-29, 8) * s, coat_dark, 8 * s)
    draw_line(Vector2(13, -15) * s, Vector2(29, 8) * s, coat_dark, 8 * s)
    draw_circle(Vector2(0, -42) * s, 16 * s, skin)
    draw_arc(Vector2(0, -45) * s, 15 * s, PI, TAU, 18, Color("#382d2a"), 7 * s)
    draw_circle(Vector2(5, -42) * s, 1.5 * s, Color("#3b302d"))

func _draw() -> void:
    var scale_value := float(entity_data.get("scale", 1.0))
    match entity_type:
        "tree": _draw_tree(scale_value)
        "campfire": _draw_fire(scale_value)
        "human": _draw_human(scale_value)
        _:
            _shadow(14.0 * scale_value, 5.0 * scale_value, 13.0 * scale_value)
            draw_circle(Vector2.ZERO, 12 * scale_value, Color("#d7e1df"))
