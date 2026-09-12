extends Node2D

const EntityVisual = preload("res://entity_visual.gd")

var socket := WebSocketPeer.new()
var world: Dictionary = {}
var connection_state := "conectando"
var last_message := "aguardando World State"
var entity_nodes: Dictionary = {}
var last_reconcile := {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}
var audience_feed: Array[String] = []
var last_action := "aguardando evento"
var last_event_id := "-"
var last_delta_id := "-"
var narration_text := "A Live Infinita está começando."
var audio_label := "Áudio local: Piper + ambiente procedural · clique ATIVAR ÁUDIO"

func _ready() -> void:
    _connect_websocket()
    _install_browser_audio_bridge()
    queue_redraw()

func _install_browser_audio_bridge() -> void:
    if not OS.has_feature("web"):
        return
    var script := """
(() => {
  if (window.__liveInfinitaAudioInstalled) return true;
  window.__liveInfinitaAudioInstalled = true;
  const audio = document.createElement('audio');
  audio.id = 'live-infinita-program-audio';
  audio.preload = 'none';
  audio.src = '/audio/live.mp3';
  audio.volume = 1.0;
  document.body.appendChild(audio);

  const btn = document.createElement('button');
  btn.id = 'live-infinita-audio-button';
  btn.textContent = '🔊 ATIVAR ÁUDIO DA LIVE';
  Object.assign(btn.style, {
    position: 'fixed', left: '50%', bottom: '18px', transform: 'translateX(-50%)',
    zIndex: '99999', padding: '14px 22px', borderRadius: '12px',
    border: '1px solid rgba(255,255,255,.35)', background: 'rgba(8,12,20,.92)',
    color: '#fff', font: '700 15px system-ui,sans-serif', cursor: 'pointer',
    boxShadow: '0 8px 30px rgba(0,0,0,.35)'
  });
  document.body.appendChild(btn);

  const start = async () => {
    try {
      audio.src = '/audio/live.mp3?ts=' + Date.now();
      await audio.play();
      btn.textContent = '🔊 ÁUDIO ATIVO';
      btn.style.background = 'rgba(18,78,44,.92)';
      setTimeout(() => { btn.style.display = 'none'; }, 1400);
      window.__liveInfinitaAudioActive = true;
    } catch (e) {
      btn.textContent = '⚠ TOQUE NOVAMENTE PARA ATIVAR ÁUDIO';
      btn.style.background = 'rgba(110,55,20,.95)';
    }
  };
  btn.addEventListener('click', start);

  const reconnect = () => {
    if (!window.__liveInfinitaAudioActive) return;
    setTimeout(async () => {
      try {
        audio.src = '/audio/live.mp3?ts=' + Date.now();
        await audio.play();
      } catch (_) {}
    }, 1200);
  };
  audio.addEventListener('ended', reconnect);
  audio.addEventListener('error', reconnect);
  return true;
})()
"""
    JavaScriptBridge.eval(script)

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
        if connection_state != "conectado":
            connection_state = "conectado"
            queue_redraw()
        while socket.get_available_packet_count() > 0:
            var text := socket.get_packet().get_string_from_utf8()
            var parsed = JSON.parse_string(text)
            if typeof(parsed) != TYPE_DICTIONARY:
                continue
            var msg: Dictionary = parsed
            var msg_type := str(msg.get("type", ""))
            if msg_type == "world_state" and typeof(msg.get("world")) == TYPE_DICTIONARY:
                _apply_world_state(msg)
            elif msg_type == "audience_event" and typeof(msg.get("event")) == TYPE_DICTIONARY:
                _apply_audience_event(msg["event"])
    elif state == WebSocketPeer.STATE_CLOSED:
        connection_state = "desconectado"
        queue_redraw()

func _apply_world_state(message: Dictionary) -> void:
    var next_world: Dictionary = message.get("world", {})
    world = next_world.duplicate(true)
    last_reconcile = _reconcile_entities(world.get("entities", []))
    last_message = "World State v%s / seq %s" % [world.get("version", "?"), world.get("sequence", "?")]

    var event = message.get("event", {})
    if typeof(event) == TYPE_DICTIONARY:
        last_action = str(event.get("action", "evento do mundo"))
        last_event_id = str(event.get("event_id", "-"))

    var delta = message.get("delta", {})
    if typeof(delta) == TYPE_DICTIONARY:
        last_delta_id = str(delta.get("delta_id", "-"))

    var narration = world.get("narration", {})
    if typeof(narration) == TYPE_DICTIONARY:
        var text := str(narration.get("text", "")).strip_edges()
        if not text.is_empty():
            narration_text = text

    queue_redraw()

func _apply_audience_event(event: Dictionary) -> void:
    var kind := str(event.get("kind", "")).strip_edges().to_lower()
    var actor = event.get("actor", {})
    var name := "Visitante"
    if typeof(actor) == TYPE_DICTIONARY:
        var display := str(actor.get("display_name", "")).strip_edges()
        var actor_id := str(actor.get("actor_id", "")).strip_edges()
        if not display.is_empty():
            name = display
        elif not actor_id.is_empty():
            name = actor_id

    var line := ""
    match kind:
        "join":
            line = "%s entrou na live" % name
        "like":
            line = "%s curtiu a live" % name
        "gift":
            line = "%s enviou um presente" % name
        _:
            line = "%s interagiu com a live" % name

    audience_feed.push_front(line)
    while audience_feed.size() > 7:
        audience_feed.pop_back()
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

func _draw_panel(rect: Rect2, border: Color) -> void:
    draw_rect(rect, Color(0.025, 0.04, 0.065, 0.88), true)
    draw_rect(rect, border, false, 2.0)

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

    var font := ThemeDB.fallback_font

    var state_panel := Rect2(20, 20, 420, 182)
    _draw_panel(state_panel, Color(0.45, 0.82, 1.0, 0.85))
    draw_string(font, Vector2(38, 50), "LIVE INFINITA · MUNDO", HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color.WHITE)
    draw_string(font, Vector2(38, 78), "WebSocket: %s" % connection_state, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("#b9dcff"))
    draw_string(font, Vector2(38, 103), last_message, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("#d5d9de"))
    draw_string(font, Vector2(38, 128), "Construção: %s" % last_action, HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color("#c9f7cf"))
    draw_string(font, Vector2(38, 153), "Event %s · Delta %s" % [last_event_id, last_delta_id], HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color("#b7c0ca"))
    draw_string(font, Vector2(38, 178), "Entidades +%s ~%s -%s =%s" % [last_reconcile["added"], last_reconcile["updated"], last_reconcile["removed"], last_reconcile["unchanged"]], HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color("#f1d18a"))

    var feed_w := 330.0
    var feed_panel := Rect2(viewport.x - feed_w - 20, 20, feed_w, 228)
    _draw_panel(feed_panel, Color(0.95, 0.53, 0.74, 0.9))
    draw_string(font, Vector2(feed_panel.position.x + 18, 50), "AO VIVO · AUDIÊNCIA", HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color.WHITE)
    if audience_feed.is_empty():
        draw_string(font, Vector2(feed_panel.position.x + 18, 82), "Aguardando participantes...", HORIZONTAL_ALIGNMENT_LEFT, feed_w - 36, 14, Color("#c8ced7"))
    else:
        var y := 82.0
        for line in audience_feed:
            draw_string(font, Vector2(feed_panel.position.x + 18, y), "• " + line, HORIZONTAL_ALIGNMENT_LEFT, feed_w - 36, 14, Color("#f4edf2"))
            y += 23.0

    var narration_panel := Rect2(90, viewport.y - 112, viewport.x - 180, 82)
    _draw_panel(narration_panel, Color(0.95, 0.78, 0.36, 0.9))
    draw_string(font, Vector2(112, viewport.y - 84), "NARRATIVA", HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color("#f8d878"))
    draw_string(font, Vector2(112, viewport.y - 56), narration_text, HORIZONTAL_ALIGNMENT_CENTER, viewport.x - 224, 19, Color.WHITE)
    draw_string(font, Vector2(112, viewport.y - 35), audio_label, HORIZONTAL_ALIGNMENT_RIGHT, viewport.x - 224, 11, Color("#aeb8c4"))
