extends Node2D

const EntityVisual = preload("res://entity_visual.gd")

var socket := WebSocketPeer.new()
var world: Dictionary = {}
var connection_state := "conectando"
var last_message := "aguardando World State"
var entity_nodes: Dictionary = {}
var last_reconcile := {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}

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
                    _apply_world_state(msg["world"])
    elif state == WebSocketPeer.STATE_CLOSED:
        connection_state = "desconectado"
        queue_redraw()

func _apply_world_state(next_world: Dictionary) -> void:
    world = next_world.duplicate(true)
    last_reconcile = _reconcile_entities(world.get("entities", []))
    last_message = "World State v%s / seq %s" % [world.get("version", "?"), world.get("sequence", "?")]
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

    var panel := Rect2(20, 20, 410, 132)
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

    var narration := str(world.get("narration", {}).get("text", ""))
    if not narration.is_empty():
        draw_rect(Rect2(110, viewport.y - 78, viewport.x - 220, 48), Color(0.02, 0.03, 0.05, 0.82), true)
        draw_string(font, Vector2(135, viewport.y - 47), narration, HORIZONTAL_ALIGNMENT_CENTER, viewport.x - 270, 18, Color.WHITE)
