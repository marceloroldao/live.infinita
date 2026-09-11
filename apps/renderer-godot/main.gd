extends Node2D

var socket := WebSocketPeer.new()
var world: Dictionary = {}
var connection_state := "conectando"
var last_message := "aguardando World State"

func _ready() -> void:
    _connect_websocket()
    queue_redraw()

func _connect_websocket() -> void:
    var url := "ws://127.0.0.1:8080/ws"
    if OS.has_feature("web"):
        var protocol = JavaScriptBridge.eval("window.location.protocol")
        var host = JavaScriptBridge.eval("window.location.host")
        var ws_scheme := "wss://" if str(protocol) == "https:" else "ws://"
        url = ws_scheme + str(host) + "/ws"
    var err := socket.connect_to_url(url)
    if err != OK:
        connection_state = "erro de conexão"
        last_message = "WebSocket error=%s" % err

func _process(_delta: float) -> void:
    socket.poll()
    var state := socket.get_ready_state()
    if state == WebSocketPeer.STATE_OPEN:
        connection_state = "conectado"
        while socket.get_available_packet_count() > 0:
            var text := socket.get_packet().get_string_from_utf8()
            var parsed = JSON.parse_string(text)
            if typeof(parsed) == TYPE_DICTIONARY:
                var msg: Dictionary = parsed
                if msg.get("type") == "world_state" and typeof(msg.get("world")) == TYPE_DICTIONARY:
                    world = msg["world"]
                    last_message = "World State v%s / seq %s" % [world.get("version", "?"), world.get("sequence", "?")]
                    queue_redraw()
    elif state == WebSocketPeer.STATE_CLOSED:
        connection_state = "desconectado"
        queue_redraw()

func _draw() -> void:
    var viewport := get_viewport_rect().size
    var period := str(world.get("environment", {}).get("period", "day"))
    var sky := Color("#132039") if period == "night" else Color("#8dd7ff")
    var ground := Color("#173d2d") if period == "night" else Color("#65a35b")
    draw_rect(Rect2(Vector2.ZERO, viewport), sky)
    draw_rect(Rect2(0, viewport.y * 0.56, viewport.x, viewport.y * 0.44), ground)

    if period == "night":
        draw_circle(Vector2(viewport.x - 110, 90), 34, Color("#f4efc8"))
    else:
        draw_circle(Vector2(viewport.x - 110, 90), 38, Color("#ffd34f"))

    var entities = world.get("entities", [])
    if typeof(entities) == TYPE_ARRAY:
        for entity in entities:
            if typeof(entity) != TYPE_DICTIONARY:
                continue
            _draw_entity(entity)

    var panel := Rect2(20, 20, 330, 104)
    draw_rect(panel, Color(0.03, 0.05, 0.08, 0.86), true)
    draw_rect(panel, Color(0.55, 0.85, 1.0, 0.8), false, 2.0)
    var font := ThemeDB.fallback_font
    draw_string(font, Vector2(38, 50), "LIVE INFINITA · GODOT", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color.WHITE)
    draw_string(font, Vector2(38, 78), "WebSocket: %s" % connection_state, HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color("#b9dcff"))
    draw_string(font, Vector2(38, 103), last_message, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("#d5d9de"))

    var narration := str(world.get("narration", {}).get("text", ""))
    if not narration.is_empty():
        draw_rect(Rect2(110, viewport.y - 78, viewport.x - 220, 48), Color(0.02, 0.03, 0.05, 0.82), true)
        draw_string(font, Vector2(135, viewport.y - 47), narration, HORIZONTAL_ALIGNMENT_CENTER, viewport.x - 270, 18, Color.WHITE)

func _draw_entity(entity: Dictionary) -> void:
    var p_data = entity.get("position", {})
    var p := Vector2(float(p_data.get("x", 0)), float(p_data.get("y", 0)))
    var scale_value := float(entity.get("scale", 1.0))
    match str(entity.get("type", "")):
        "tree":
            draw_rect(Rect2(p.x - 13 * scale_value, p.y, 26 * scale_value, 95 * scale_value), Color("#6c4428"), true)
            draw_circle(p + Vector2(0, -8), 60 * scale_value, Color("#286542"))
            draw_circle(p + Vector2(-35, 18), 42 * scale_value, Color("#347d4d"))
            draw_circle(p + Vector2(34, 18), 42 * scale_value, Color("#347d4d"))
        "campfire":
            draw_line(p + Vector2(-25, 20), p + Vector2(25, -12), Color("#6d4b31"), 9)
            draw_line(p + Vector2(-25, -12), p + Vector2(25, 20), Color("#6d4b31"), 9)
            if bool(entity.get("properties", {}).get("lit", false)):
                draw_circle(p + Vector2(0, -12), 31, Color("#ff7c2d"))
                draw_circle(p + Vector2(0, -20), 19, Color("#ffd24a"))
        "human":
            draw_circle(p + Vector2(0, -42), 15 * scale_value, Color("#f0c7a0"))
            draw_line(p + Vector2(0, -27), p + Vector2(0, 22), Color("#384d88"), 15 * scale_value)
            draw_line(p + Vector2(0, -4), p + Vector2(-22, 12), Color("#384d88"), 8 * scale_value)
            draw_line(p + Vector2(0, -4), p + Vector2(22, 12), Color("#384d88"), 8 * scale_value)
            draw_line(p + Vector2(0, 20), p + Vector2(-15, 50), Color("#26304e"), 8 * scale_value)
            draw_line(p + Vector2(0, 20), p + Vector2(15, 50), Color("#26304e"), 8 * scale_value)
