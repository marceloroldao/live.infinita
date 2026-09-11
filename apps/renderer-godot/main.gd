extends Node2D

const EntityVisual = preload("res://entity_visual.gd")

var socket := WebSocketPeer.new()
var world: Dictionary = {}
var connection_state := "conectando"
var last_message := "aguardando World State"
var entity_nodes: Dictionary = {}
var last_reconcile := {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}
var request_in_flight := false
var control_status := "controles prontos"
var http_request: HTTPRequest

func _ready() -> void:
    _build_debug_controls()
    _connect_websocket()
    queue_redraw()

func _build_debug_controls() -> void:
    http_request = HTTPRequest.new()
    http_request.name = "DebugHTTPRequest"
    http_request.request_completed.connect(_on_debug_request_completed)
    add_child(http_request)

    var layer := CanvasLayer.new()
    layer.name = "DebugControls"
    layer.layer = 20
    add_child(layer)

    var panel := PanelContainer.new()
    panel.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
    panel.position = Vector2(-325, -118)
    panel.custom_minimum_size = Vector2(650, 92)
    layer.add_child(panel)

    var vbox := VBoxContainer.new()
    vbox.add_theme_constant_override("separation", 6)
    panel.add_child(vbox)

    var title := Label.new()
    title.text = "TESTE AO VIVO — mantenha esta tela aberta"
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    vbox.add_child(title)

    var row := HBoxContainer.new()
    row.alignment = BoxContainer.ALIGNMENT_CENTER
    row.add_theme_constant_override("separation", 6)
    vbox.add_child(row)

    _add_action_button(row, "Dia", "set_day")
    _add_action_button(row, "Noite", "set_night")
    _add_action_button(row, "Fogueira", "toggle_fire")
    _add_action_button(row, "Mover árvore", "move_tree")
    _add_action_button(row, "+ Visitante", "spawn_person")

func _add_action_button(parent: Control, label: String, action: String) -> void:
    var button := Button.new()
    button.text = label
    button.custom_minimum_size = Vector2(112, 38)
    button.pressed.connect(func(): _send_debug_action(action))
    parent.add_child(button)

func _api_base_url() -> String:
    if OS.has_feature("web"):
        var origin = JavaScriptBridge.eval("window.location.origin")
        return str(origin)
    return "http://127.0.0.1:8080"

func _send_debug_action(action: String) -> void:
    if request_in_flight:
        control_status = "aguardando resposta anterior"
        queue_redraw()
        return
    request_in_flight = true
    control_status = "enviando %s..." % action
    queue_redraw()
    var headers := PackedStringArray(["Content-Type: application/json"])
    var body := JSON.stringify({"action": action})
    var err := http_request.request(
        _api_base_url() + "/api/simulate",
        headers,
        HTTPClient.METHOD_POST,
        body
    )
    if err != OK:
        request_in_flight = false
        control_status = "erro HTTPRequest=%s" % err
        queue_redraw()

func _on_debug_request_completed(_result: int, response_code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
    request_in_flight = false
    control_status = "POST concluído HTTP %s — aguardando WebSocket" % response_code
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
                    _apply_world_state(msg["world"])
    elif state == WebSocketPeer.STATE_CLOSED:
        connection_state = "desconectado"
        queue_redraw()

func _apply_world_state(next_world: Dictionary) -> void:
    world = next_world.duplicate(true)
    last_reconcile = _reconcile_entities(world.get("entities", []))
    last_message = "World State v%s / seq %s" % [world.get("version", "?"), world.get("sequence", "?")]
    control_status = "World State recebido via WebSocket"
    queue_redraw()

func _reconcile_entities(entities) -> Dictionary:
    var result := {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}
    var seen: Dictionary = {}

    if typeof(entities) == TYPE_ARRAY:
        for entity in entities:
            if typeof(entity) != TYPE_DICTIONARY:
                continue
            var entity_id := str(entity.get("id", "")).strip_edges()
            if entity_id.is_empty():
                continue
            seen[entity_id] = true

            if not entity_nodes.has(entity_id):
                var visual = EntityVisual.new()
                visual.name = "Entity_%s" % entity_id
                add_child(visual)
                entity_nodes[entity_id] = visual
                visual.apply_entity(entity)
                result["added"] += 1
            else:
                var visual = entity_nodes[entity_id]
                if visual.apply_entity(entity):
                    result["updated"] += 1
                else:
                    result["unchanged"] += 1

    var known_ids := entity_nodes.keys().duplicate()
    for entity_id in known_ids:
        if not seen.has(entity_id):
            var visual = entity_nodes[entity_id]
            entity_nodes.erase(entity_id)
            visual.queue_free()
            result["removed"] += 1

    return result

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

    var panel := Rect2(20, 20, 440, 158)
    draw_rect(panel, Color(0.03, 0.05, 0.08, 0.86), true)
    draw_rect(panel, Color(0.55, 0.85, 1.0, 0.8), false, 2.0)
    var font := ThemeDB.fallback_font
    draw_string(font, Vector2(38, 50), "LIVE INFINITA · GODOT", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color.WHITE)
    draw_string(font, Vector2(38, 78), "WebSocket: %s" % connection_state, HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color("#b9dcff"))
    draw_string(font, Vector2(38, 103), last_message, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("#d5d9de"))
    draw_string(
        font,
        Vector2(38, 128),
        "Reconcile +%s ~%s -%s =%s" % [last_reconcile["added"], last_reconcile["updated"], last_reconcile["removed"], last_reconcile["unchanged"]],
        HORIZONTAL_ALIGNMENT_LEFT,
        -1,
        15,
        Color("#c9f7cf")
    )
    draw_string(font, Vector2(38, 153), control_status, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color("#f3d89b"))

    var narration := str(world.get("narration", {}).get("text", ""))
    if not narration.is_empty():
        draw_rect(Rect2(110, viewport.y - 148, viewport.x - 220, 48), Color(0.02, 0.03, 0.05, 0.82), true)
        draw_string(font, Vector2(135, viewport.y - 117), narration, HORIZONTAL_ALIGNMENT_CENTER, viewport.x - 270, 18, Color.WHITE)
