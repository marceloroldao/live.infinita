extends CanvasLayer

var _brand: Control
var _narration: Label
var _audience: Label
var _narration_remaining := 0.0
var _audience_remaining := 0.0
var _last_narration := ""
var _audience_feed: Array[String] = []

func _ready() -> void:
    layer = 10
    var layout := Control.new()
    layout.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    layout.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(layout)
    _brand = Control.new()
    _brand.name = "LiveInfinitaBrand"
    _brand.mouse_filter = Control.MOUSE_FILTER_IGNORE
    _brand.anchor_right = 1.0
    _brand.offset_bottom = 90
    layout.add_child(_brand)
    _brand.draw.connect(_draw_brand)
    _brand.resized.connect(_brand.queue_redraw)
    _audience = _label(layout, 18, 104, 18)
    _audience.offset_right = -18
    _audience.anchor_right = 1.0
    _audience.offset_bottom = 302
    _narration = _label(layout, 18, -81, 20)
    _narration.anchor_top = 0.5
    _narration.anchor_bottom = 0.5
    _narration.anchor_right = 1.0
    _narration.offset_right = -18
    _narration.offset_bottom = 81
    _narration.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    _narration.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    _narration.visible = false
    _audience.visible = false

func _draw_brand() -> void:
    # Restore the original broadcast mark, including tagline and live badge.
    var scale := clampf(_brand.size.x / 720.0, 0.5, 1.0)
    var width := _brand.size.x / scale
    var font := ThemeDB.fallback_font
    _brand.draw_set_transform(Vector2.ZERO, 0.0, Vector2(scale, scale))
    _brand.draw_circle(Vector2(46,52),15,Color(0.36,0.84,0.96,0.16))
    _brand.draw_circle(Vector2(46,52),7,Color("#77d9ef"))
    _brand.draw_string(font,Vector2(72,57),"LIVE INFINITA",HORIZONTAL_ALIGNMENT_LEFT,-1,22,Color.WHITE)
    _brand.draw_string(font,Vector2(72,78),"um mundo que continua",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color(0.84,0.91,0.94,0.82))
    var rect := Rect2(width-126,34,96,34)
    var style := StyleBoxFlat.new()
    style.bg_color = Color(0.35,0.05,0.08,0.82)
    style.border_color = Color(1,0.25,0.34,0.55)
    style.set_border_width_all(1)
    style.set_corner_radius_all(14)
    _brand.draw_style_box(style,rect)
    _brand.draw_circle(rect.position+Vector2(16,17),4.5,Color("#ff4055"))
    _brand.draw_string(font,rect.position+Vector2(29,23),"AO VIVO",HORIZONTAL_ALIGNMENT_LEFT,-1,13,Color.WHITE)

func _label(parent: Control, x: float, y: float, size: int) -> Label:
    var label := Label.new()
    label.position = Vector2(x, y)
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.add_theme_font_size_override("font_size", size)
    label.add_theme_color_override("font_color", Color.WHITE)
    label.add_theme_color_override("font_shadow_color", Color.BLACK)
    label.add_theme_constant_override("shadow_offset_x", 2)
    label.add_theme_constant_override("shadow_offset_y", 2)
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    parent.add_child(label)
    return label

func apply_program_state(world: Dictionary) -> void:
    var narration = world.get("narration", {})
    if typeof(narration) != TYPE_DICTIONARY:
        return
    var text := str(narration.get("text", "")).strip_edges()
    if text.is_empty() or text == _last_narration:
        return
    _last_narration = text
    _narration.text = "NARRADOR\n" + text.left(480)
    _narration_remaining = clampf(float(text.length()) * 0.075, 8.0, 20.0)
    _narration.visible = true

func apply_audience_event(event: Dictionary) -> void:
    var kind := str(event.get("kind", "")).strip_edges().to_lower()
    var actor = event.get("actor", {})
    var name := "Visitante"
    if typeof(actor) == TYPE_DICTIONARY:
        var display := str(actor.get("display_name", "")).strip_edges()
        var actor_id := str(actor.get("actor_id", "")).strip_edges()
        name = display if not display.is_empty() else (actor_id if not actor_id.is_empty() else name)
    name = name.left(48).replace("\n", " ")
    var line := "%s interagiu" % name
    match kind:
        "join": line = "%s entrou" % name
        "like": line = "%s curtiu" % name
        "gift": line = "%s enviou um presente" % name
        "text", "comment":
            var text := str(event.get("text", "")).strip_edges().replace("\n", " ").left(120)
            if not text.is_empty():
                line = "%s: %s" % [name, text]
    _audience_feed.push_front(line)
    while _audience_feed.size() > 4:
        _audience_feed.pop_back()
    _audience.text = "AUDIÊNCIA\n" + "\n".join(_audience_feed)
    _audience_remaining = 12.0
    _audience.visible = true

func _process(delta: float) -> void:
    _narration_remaining = maxf(0.0, _narration_remaining - delta)
    _audience_remaining = maxf(0.0, _audience_remaining - delta)
    if _narration != null:
        _narration.visible = _narration_remaining > 0.0
    if _audience != null:
        _audience.visible = _audience_remaining > 0.0
