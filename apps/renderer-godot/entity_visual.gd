extends Node2D

const LOGICAL_WORLD_SIZE := Vector2(1280.0, 720.0)
const PORTRAIT_STAGE := Rect2(90.0, 330.0, 540.0, 620.0)
const HUMAN_WALK_SPEED := 48.0
const HUMAN_WALK_ACCEL := 150.0
const HUMAN_WALK_DECEL := 210.0
const HUMAN_STOP_RADIUS := 1.5

var entity_id: String = ""
var entity_type: String = ""
var entity_data: Dictionary = {}
var data_signature: String = ""
var world_position := Vector2.ZERO
var target_position := Vector2.ZERO
var target_presentation_scale := 1.0
var visual_time := 0.0
var walk_velocity := Vector2.ZERO
var walk_phase := 0.0
var walk_blend := 0.0
var facing_sign := 1.0
var camera_offset := Vector2.ZERO
var night_amount := 0.0
var wind_amount := 0.25
var variant := 0
var arrival := 0.0

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
    variant = absi(entity_id.hash())
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

func _is_walking() -> bool:
    return entity_type == "human" and (walk_blend > 0.08 or position.distance_to(target_position) > HUMAN_STOP_RADIUS)

func _advance_human_walk(delta: float) -> void:
    var was_moving := walk_velocity.length() > 3.0
    var offset := target_position - position
    var distance := offset.length()
    if distance > HUMAN_STOP_RADIUS:
        var direction := offset / distance
        if absf(direction.x) > 0.08:
            facing_sign = 1.0 if direction.x >= 0.0 else -1.0
        # Slow down near the destination instead of stopping abruptly.
        var approach := clampf(distance / 34.0, 0.34, 1.0)
        var desired_velocity := direction * HUMAN_WALK_SPEED * approach
        walk_velocity = walk_velocity.move_toward(desired_velocity, HUMAN_WALK_ACCEL * delta)
        var step := walk_velocity * delta
        if step.length() >= distance:
            position = target_position
            walk_velocity = Vector2.ZERO
        else:
            position += step
    else:
        position = target_position
        walk_velocity = walk_velocity.move_toward(Vector2.ZERO, HUMAN_WALK_DECEL * delta)

    if was_moving and walk_velocity.length() <= 3.0: arrival = 1.0
    var speed_ratio := clampf(walk_velocity.length() / HUMAN_WALK_SPEED, 0.0, 1.0)
    walk_blend = move_toward(walk_blend, speed_ratio, delta * 5.5)
    # Cadence follows actual presentation speed, so feet do not skate when slowing.
    walk_phase = fmod(walk_phase + delta * lerpf(4.2, 9.2, speed_ratio), TAU)

func _process(delta: float) -> void:
    visual_time += delta
    arrival = maxf(0.0, arrival - delta * 2.2)
    if entity_type == "human":
        _advance_human_walk(delta)
    else:
        position = position.lerp(target_position, minf(1.0, delta * 3.8))
    var uniform: float = scale.x
    uniform = lerpf(uniform, target_presentation_scale, minf(1.0, delta * 3.2))
    scale = Vector2.ONE * uniform
    # Humans redraw even while stopped so breathing/idle sway keeps the scene alive.
    if get_viewport_rect().grow(180.0).has_point(position + camera_offset):
        queue_redraw()

func _shadow(radius_x: float, radius_y: float, offset_y: float = 44.0) -> void:
    draw_set_transform(camera_offset + Vector2(0, offset_y), 0.0, Vector2(1.0, radius_y / maxf(radius_x, 1.0)))
    draw_circle(Vector2.ZERO, radius_x, Color(0.02, 0.04, 0.04, 0.22 - night_amount * 0.06))
    draw_set_transform(camera_offset, 0.0, Vector2.ONE)

func _draw_tree(s: float) -> void:
    var height := 0.86 + float(variant % 29) / 100.0
    var width := 0.83 + float((variant / 31) % 35) / 100.0
    var phase := float(variant % 101) * 0.13
    var sway := sin(visual_time * (0.65 + float(variant % 7) * 0.055) + phase) * (0.7 + wind_amount * 7.0) * s
    var dark := Color("#244c3a").lerp(Color("#142e32"), night_amount)
    var mid := Color("#49764b").lerp(Color("#294844"), night_amount)
    var light := Color("#739354").lerp(Color("#3d6051"), night_amount)
    mid = mid.lightened(float(variant % 9) * 0.008)
    _shadow(49 * s * width, 13 * s, 73 * s)
    draw_colored_polygon(PackedVector2Array([Vector2(-14, 72) * s, Vector2(-8, -42 * height) * s, Vector2(9, -39 * height) * s, Vector2(17, 72) * s]), Color("#70533a").lerp(Color("#3a3732"), night_amount))
    draw_line(Vector2(-3, 62) * s, Vector2(-2, -34 * height) * s, Color(0.84, 0.67, 0.43, 0.2), 3 * s, true)
    for i in range(3 + variant % 3):
        var sign_x := -1.0 if i % 2 == 0 else 1.0
        draw_line(Vector2(0, 12 - i * 13) * s, Vector2(sign_x * (25 + i * 3) + sway, -25 - i * 10) * s, Color("#655039").lerp(Color("#34362f"), night_amount), (6 - i * 0.6) * s, true)
    # A seeded cluster of layered crowns gives each entity a stable silhouette.
    for i in range(7 + variant % 3):
        var angle := float(i) * 2.399 + phase
        var radial := 24.0 + float((variant + i * 17) % 21)
        var center := Vector2(cos(angle) * radial * width, -36 * height + sin(angle) * radial * 0.75 * height) * s
        center.x += sway * (0.65 + float(i % 3) * 0.2)
        var radius := (27.0 + float((variant + i * 11) % 13)) * s
        draw_circle(center + Vector2(2, 6) * s, radius, dark)
        draw_circle(center, radius * 0.90, mid if i % 3 != 0 else light)
        draw_arc(center + Vector2(-3, -2) * s, radius * 0.65, 3.6, 4.9, 9, Color(0.79, 0.86, 0.57, 0.12 * (1.0 - night_amount)), 2 * s, true)
    for i in range(5):
        var base := Vector2(-30.0 + i * 15.0, 72.0) * s
        draw_line(base, base + Vector2(sway * 0.6, -7 - i % 3 * 3) * s, mid, 2 * s, true)

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
    var pulse := 1.0 + sin(visual_time * 1.7) * 0.035 + sin(visual_time * 2.9) * 0.018
    # Soft ground illumination is layered, bounded, and fades with daylight.
    for ring in range(12, 0, -1):
        draw_set_transform(camera_offset + Vector2(0, 16) * s, 0.0, Vector2(1.0, 0.42))
        draw_circle(Vector2.ZERO, (30.0 + ring * 9.0) * s * pulse, Color(1.0, 0.59, 0.22, (0.004 + night_amount * 0.015)))
    draw_set_transform(camera_offset)
    for stone in range(9):
        var angle := float(stone) / 9.0 * TAU
        var pos := Vector2(cos(angle) * 33.0, sin(angle) * 12.0 + 16.0) * s
        draw_circle(pos, 5.5 * s, Color("#8d8871").lerp(Color("#716150"), night_amount))
    var flicker := sin(visual_time * 4.1) * 4.0 + sin(visual_time * 6.7) * 2.0
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
    var walking := _is_walking()
    var blend := walk_blend if walking else 0.0
    var idle_blend := 1.0 - clampf(blend, 0.0, 1.0)
    var idle_breath := sin(visual_time * 1.8 + float(abs(entity_id.hash()) % 7)) * 0.85 * idle_blend
    var idle_sway := sin(visual_time * 0.72 + float(abs(entity_id.hash()) % 5)) * 0.65 * idle_blend
    var stride := sin(walk_phase) * blend
    var opposite := sin(walk_phase + PI) * blend
    var bob := absf(sin(walk_phase)) * 2.4 * blend + idle_breath + sin(arrival * PI) * 1.6
    var torso_sway := sin(walk_phase) * 1.6 * blend + idle_sway
    var leg_swing := stride * 12.0
    var arm_swing := opposite * 9.0
    var lean := clampf(walk_velocity.x / HUMAN_WALK_SPEED, -1.0, 1.0) * 2.2 * blend

    _shadow((28.0 + 3.0 * blend) * s, 10.0 * s, 46.0 * s)
    var skin := Color("#e8b98e").lerp(Color("#ac9d96"), night_amount * 0.55)
    var coat := Color("#435a83")
    var coat_dark := Color("#2d3f62")

    # Feet/legs alternate naturally instead of opening and closing in sync.
    draw_line(Vector2(-6 + torso_sway, 15 + bob) * s, Vector2(-15 + leg_swing, 49) * s, Color("#26334b"), 9 * s)
    draw_line(Vector2(6 + torso_sway, 15 + bob) * s, Vector2(15 - leg_swing, 49) * s, Color("#26334b"), 9 * s)
    draw_line(Vector2(-18 + leg_swing, 49) * s, Vector2(-7 + leg_swing, 49) * s, Color("#1d273b"), 5 * s)
    draw_line(Vector2(12 - leg_swing, 49) * s, Vector2(23 - leg_swing, 49) * s, Color("#1d273b"), 5 * s)

    draw_colored_polygon(PackedVector2Array([
        Vector2(-17 + lean + idle_sway, -23 + bob) * s, Vector2(16 + lean + idle_sway, -23 + bob) * s,
        Vector2(13 + torso_sway, 22 + bob) * s, Vector2(-13 + torso_sway, 22 + bob) * s
    ]), coat)

    # Arms swing opposite to the legs. While idle they inherit a tiny breathing sway.
    var idle_arm := idle_sway * 1.6
    draw_line(Vector2(-13 + lean, -15 + bob) * s, Vector2(-27, 8 + bob + arm_swing + idle_arm) * s, coat_dark, 8 * s)
    draw_line(Vector2(13 + lean, -15 + bob) * s, Vector2(27, 8 + bob - arm_swing - idle_arm) * s, coat_dark, 8 * s)

    # Scarf and coat seam make NOV recognizable at portrait preview size.
    draw_line(Vector2(-12 + lean, -22 + bob) * s, Vector2(12 + lean, -22 + bob) * s, Color("#d7a85c"), 5 * s, true)
    draw_line(Vector2(8 + lean, -20 + bob) * s, Vector2(12 + lean + sin(visual_time * 1.3) * (1 + wind_amount * 3), -7 + bob) * s, Color("#c78b4a"), 4 * s, true)
    draw_line(Vector2(torso_sway, -13 + bob) * s, Vector2(torso_sway, 18 + bob) * s, Color(0.8, 0.86, 0.9, 0.18), 1 * s, true)
    if blend > 0.2:
        for i in range(3):
            var phase := fmod(walk_phase / TAU + i * 0.33, 1.0)
            draw_circle(Vector2(-facing_sign * phase * 20, 49 - phase * 7) * s, (1 + phase * 2) * s, Color(0.77, 0.72, 0.53, (1.0 - phase) * blend * 0.16))
    var head_x := lean * 0.65 + idle_sway * 0.45
    draw_circle(Vector2(head_x, -42 + bob) * s, 16 * s, skin)
    draw_arc(Vector2(head_x, -45 + bob) * s, 15 * s, PI, TAU, 18, Color("#382d2a"), 7 * s)
    # Eye subtly indicates the current horizontal walking direction.
    var blink := fmod(visual_time + float(variant % 7), 5.7) < 0.13
    if blink:
        draw_line(Vector2(head_x + 3 * facing_sign, -42 + bob) * s, Vector2(head_x + 7 * facing_sign, -42 + bob) * s, Color("#3b302d"), 1 * s)
    else:
        draw_circle(Vector2(head_x + 5.0 * facing_sign, -42 + bob) * s, 1.5 * s, Color("#3b302d"))

func _draw() -> void:
    draw_set_transform(camera_offset)
    var scale_value := float(entity_data.get("scale", 1.0))
    match entity_type:
        "tree": _draw_tree(scale_value)
        "campfire": _draw_fire(scale_value)
        "human": _draw_human(scale_value)
        "house", "shelter", "safe_place": _draw_shelter(scale_value)
        "rest_point": _draw_rest(scale_value)
        _:
            _shadow(14.0 * scale_value, 5.0 * scale_value, 13.0 * scale_value)
            draw_circle(Vector2.ZERO, 12 * scale_value, Color("#d7e1df"))

func _draw_rest(s: float) -> void:
    _shadow(28 * s, 9 * s, 22 * s)
    draw_line(Vector2(-22, 23) * s, Vector2(-22, 4) * s, Color("#654c37"), 5 * s)
    draw_line(Vector2(22, 23) * s, Vector2(22, 4) * s, Color("#654c37"), 5 * s)
    draw_line(Vector2(-29, 3) * s, Vector2(29, 3) * s, Color("#a28e62"), 9 * s)

func _draw_shelter(s: float) -> void:
    # Only materialized shelter entities receive architecture; no invented houses.
    _shadow(57 * s, 16 * s, 38 * s)
    var plaster := Color("#c2b692").lerp(Color("#667777"), night_amount)
    draw_rect(Rect2(Vector2(-43, -34) * s, Vector2(86, 70) * s), plaster)
    draw_colored_polygon(PackedVector2Array([Vector2(-54, -29) * s, Vector2(-5, -80) * s, Vector2(54, -29) * s]), Color("#73574e").lerp(Color("#394659"), night_amount))
    draw_line(Vector2(-52, -29) * s, Vector2(-5, -78) * s, Color("#b3956b"), 4 * s, true)
    draw_rect(Rect2(Vector2(-9, 0) * s, Vector2(22, 36) * s), Color("#4b4940"))
    var glow := Color("#a8c1b3").lerp(Color("#f7ce79"), night_amount)
    draw_rect(Rect2(Vector2(-32, -17) * s, Vector2(16, 20) * s), glow)
    draw_line(Vector2(-24, -17) * s, Vector2(-24, 3) * s, Color("#685843"), 2 * s)
    for ring in range(5, 0, -1):
        draw_circle(Vector2(-24, -7) * s, (12 + ring * 5) * s, Color(1.0, 0.73, 0.34, night_amount * 0.018))
    # Short path and fence remain tied to this hot entity's lifetime.
    for i in range(4):
        draw_line(Vector2(-64 + i * 10, 33) * s, Vector2(-64 + i * 10, 16) * s, Color("#93805b"), 3 * s)
    draw_line(Vector2(-66, 23) * s, Vector2(-32, 23) * s, Color("#93805b"), 3 * s)
    for i in range(4):
        draw_set_transform(camera_offset + Vector2(3 + sin(i * 1.2) * 4, 42 + i * 9) * s, 0.0, Vector2(1.4, 0.45))
        draw_circle(Vector2.ZERO, 5 * s, plaster.darkened(0.15))
    draw_set_transform(camera_offset)
