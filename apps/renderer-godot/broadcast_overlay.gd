extends Node2D

@onready var stage = get_parent()
var panel_styles: Dictionary = {}

func _process(_delta: float) -> void:
    queue_redraw()

func _draw() -> void:
    var viewport := Vector2(720, 1280)
    var font := ThemeDB.fallback_font
    _draw_brand(font, viewport)
    _draw_audience(font, viewport)
    _draw_narration(font, viewport)
    _draw_collective(font, viewport)
    _draw_safe_guides(viewport)

func _panel_style(fill: Color, border: Color, radius: int = 18) -> StyleBoxFlat:
    var key := str(fill) + str(border) + str(radius)
    if panel_styles.has(key): return panel_styles[key]
    var style := StyleBoxFlat.new(); style.bg_color = fill; style.border_color = border; style.set_border_width_all(1)
    style.corner_radius_top_left = radius; style.corner_radius_top_right = radius; style.corner_radius_bottom_left = radius; style.corner_radius_bottom_right = radius
    style.shadow_color = Color(0,0,0,0.24); style.shadow_size = 12
    panel_styles[key] = style
    return style

func _draw_brand(font: Font, v: Vector2) -> void:
    draw_circle(Vector2(46,52),15,Color(0.36,0.84,0.96,0.16)); draw_circle(Vector2(46,52),7,Color("#77d9ef"))
    draw_string(font,Vector2(72,57),"LIVE INFINITA",HORIZONTAL_ALIGNMENT_LEFT,-1,22,Color.WHITE)
    draw_string(font,Vector2(72,78),"um mundo que continua",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color(0.84,0.91,0.94,0.82))
    var r := Rect2(v.x-126,34,96,34); draw_style_box(_panel_style(Color(0.35,0.05,0.08,0.82),Color(1,0.25,0.34,0.55),14),r)
    draw_circle(Vector2(r.position.x+16,r.position.y+17),4.5,Color("#ff4055")); draw_string(font,r.position+Vector2(29,23),"AO VIVO",HORIZONTAL_ALIGNMENT_LEFT,-1,13,Color.WHITE)

func _draw_audience(font: Font, v: Vector2) -> void:
    if stage.audience_feed.is_empty() or stage.audience_remaining <= 0.0: return
    var width := v.x-60.0; var height: float = 48.0+stage.audience_feed.size()*25.0; var r := Rect2(30,102,width,height)
    draw_style_box(_panel_style(Color(0.025,0.045,0.07,0.48),Color(0.76,0.48,0.76,0.34)),r)
    draw_string(font,r.position+Vector2(18,26),"AGORA NA LIVE",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color(0.95,0.80,0.95,0.9))
    var y := r.position.y+53
    for i in range(stage.audience_feed.size()):
        var alpha := 1.0-float(i)*0.14; draw_circle(Vector2(r.position.x+20,y-5),3.5,Color(0.97,0.63,0.79,alpha)); draw_string(font,Vector2(r.position.x+33,y),stage.audience_feed[i],HORIZONTAL_ALIGNMENT_LEFT,width-52,14,Color(1,1,1,alpha)); y += 25

func _draw_narration(font: Font, v: Vector2) -> void:
    if stage.narration_remaining <= 0.0 or stage.narration_text.is_empty(): return
    var r := Rect2(30,v.y-196,v.x-60,128)
    draw_style_box(_panel_style(Color(0.02,0.04,0.06,0.72),Color(0.93,0.72,0.32,0.40)),r)
    draw_string(font,r.position+Vector2(20,28),"NARRADOR",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color("#f5d47c"))
    draw_multiline_string(font,r.position+Vector2(20,59),stage.narration_text,HORIZONTAL_ALIGNMENT_CENTER,r.size.x-40,20,3,Color.WHITE)

func _draw_safe_guides(v: Vector2) -> void:
    if not OS.has_feature("web"): return
    var guides = JavaScriptBridge.eval("new URLSearchParams(window.location.search).get('guides')")
    if str(guides) != "1": return
    draw_rect(Rect2(24,24,v.x-48,v.y-48),Color(1,1,1,0.22),false,1)
    draw_rect(Rect2(24,96,v.x-48,v.y-250),Color(1,0.75,0.25,0.30),false,1)

func _draw_collective(font: Font, v: Vector2) -> void:
    var intent = stage.world.get("collective_intent", {})
    if typeof(intent) != TYPE_DICTIONARY or not bool(intent.get("applied", false)): return
    var chapter := int(intent.get("chapter", 0))
    if chapter <= 0: return
    draw_circle(Vector2(42, v.y - 42), 3.0, Color("#e2c285"))
    draw_string(font, Vector2(54, v.y - 37), "CAPÍTULO %d · construído juntos" % chapter, HORIZONTAL_ALIGNMENT_LEFT, v.x - 100, 13, Color(0.9, 0.9, 0.8, 0.8))


