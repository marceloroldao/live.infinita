extends Node2D

const EntityVisual = preload("res://entity_visual.gd")
const WS_RECONNECT_MAX_MS := 30000

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
var audio_label := "Áudio local · narrador e ambiente procedural"
var ws_reconnect_attempt := 0
var ws_reconnect_at_ms := 0
var visual_time := 0.0

func _ready() -> void:
    _connect_websocket()
    _install_browser_audio_bridge()
    queue_redraw()

func _install_browser_audio_bridge() -> void:
    if not OS.has_feature("web"):
        return
    var script := """
(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('capture') === '1') {
    window.__liveInfinitaCaptureMode = true;
    return true;
  }
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

  let reconnectTimer = null;
  const reconnect = () => {
    if (!window.__liveInfinitaAudioActive || reconnectTimer !== null) return;
    reconnectTimer = setTimeout(async () => {
      reconnectTimer = null;
      try {
        audio.src = '/audio/live.mp3?ts=' + Date.now();
        await audio.play();
      } catch (_) {
        reconnect();
      }
    }, 1200);
  };
  audio.addEventListener('ended', reconnect);
  audio.addEventListener('error', reconnect);
  return true;
})()
"""
    JavaScriptBridge.eval(script)

func _websocket_url() -> String:
    if OS.has_feature("web"):
        var protocol = JavaScriptBridge.eval("window.location.protocol")
        var host = JavaScriptBridge.eval("window.location.host")
        var ws_scheme := "wss://" if str(protocol) == "https:" else "ws://"
        return ws_scheme + str(host) + "/ws"
    return "ws://127.0.0.1:8080/ws"

func _connect_websocket() -> void:
    connection_state = "conectando"
    var err := socket.connect_to_url(_websocket_url())
    if err != OK:
        connection_state = "erro de conexão"
        last_message = "WebSocket error=%s" % err
        _schedule_websocket_reconnect()
    queue_redraw()

func _schedule_websocket_reconnect() -> void:
    if ws_reconnect_at_ms != 0:
        return
    var exponent := min(ws_reconnect_attempt, 5)
    var delay_ms := min(WS_RECONNECT_MAX_MS, int(1000.0 * pow(2.0, float(exponent))))
    ws_reconnect_attempt += 1
    ws_reconnect_at_ms = Time.get_ticks_msec() + delay_ms
    last_message = "Reconectando World State em %.1fs" % (float(delay_ms) / 1000.0)
    queue_redraw()

func _maybe_reconnect_websocket() -> void:
    if ws_reconnect_at_ms == 0 or Time.get_ticks_msec() < ws_reconnect_at_ms:
        return
    ws_reconnect_at_ms = 0
    socket = WebSocketPeer.new()
    _connect_websocket()

func _process(delta: float) -> void:
    visual_time += delta
    socket.poll()
    var state := socket.get_ready_state()
    if state == WebSocketPeer.STATE_OPEN:
        if connection_state != "conectado":
            connection_state = "conectado"
            ws_reconnect_attempt = 0
            ws_reconnect_at_ms = 0
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
        if connection_state != "desconectado":
            connection_state = "desconectado"
            _schedule_websocket_reconnect()
        _maybe_reconnect_websocket()
    else:
        _maybe_reconnect_websocket()
    # Subtle atmospheric motion keeps the broadcast alive even without events.
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
        "join": line = "%s entrou" % name
        "like": line = "%s curtiu" % name
        "gift": line = "%s enviou um presente" % name
        _: line = "%s interagiu" % name

    audience_feed.push_front(line)
    while audience_feed.size() > 5:
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
                if visual.apply_entity(entity): result["updated"] += 1
                else: result["unchanged"] += 1

    var known_ids := entity_nodes.keys().duplicate()
    for entity_id in known_ids:
        if not seen.has(entity_id):
            var visual = entity_nodes[entity_id]
            entity_nodes.erase(entity_id)
            visual.queue_free()
            result["removed"] += 1
    return result

func _rounded_panel(rect: Rect2, border: Color, fill_alpha: float = 0.72) -> void:
    draw_style_box(_panel_style(Color(0.025, 0.045, 0.07, fill_alpha), border), rect)

func _panel_style(fill: Color, border: Color) -> StyleBoxFlat:
    var style := StyleBoxFlat.new()
    style.bg_color = fill
    style.border_color = border
    style.set_border_width_all(1)
    style.corner_radius_top_left = 14
    style.corner_radius_top_right = 14
    style.corner_radius_bottom_left = 14
    style.corner_radius_bottom_right = 14
    style.shadow_color = Color(0, 0, 0, 0.22)
    style.shadow_size = 10
    return style

func _draw_sky(viewport: Vector2, night: bool) -> void:
    var top := Color("#08121f") if night else Color("#76b9dc")
    var bottom := Color("#24425b") if night else Color("#d4e6d5")
    var bands := 12
    for i in range(bands):
        var t := float(i) / float(bands - 1)
        var c := top.lerp(bottom, t)
        draw_rect(Rect2(0, viewport.y * t * 0.62, viewport.x, viewport.y * 0.62 / bands + 2), c)

    if night:
        for i in range(24):
            var x := fmod(float(i * 149 + 61), viewport.x - 80.0) + 40.0
            var y := fmod(float(i * 83 + 29), viewport.y * 0.42) + 24.0
            var twinkle := 0.48 + 0.35 * sin(visual_time * 1.6 + i)
            draw_circle(Vector2(x, y), 1.2 + float(i % 3) * 0.35, Color(0.92, 0.95, 1.0, twinkle))
        draw_circle(Vector2(viewport.x - 125, 96), 39, Color(0.95, 0.94, 0.79, 0.10))
        draw_circle(Vector2(viewport.x - 125, 96), 29, Color("#f2edc8"))
    else:
        draw_circle(Vector2(viewport.x - 125, 96), 56, Color(1.0, 0.77, 0.30, 0.10))
        draw_circle(Vector2(viewport.x - 125, 96), 33, Color("#f8c75e"))
        # slow clouds
        for i in range(3):
            var cloud_x := fmod(110.0 + i * 410.0 + visual_time * (5.0 + i), viewport.x + 220.0) - 110.0
            var cloud_y := 95.0 + i * 52.0
            draw_circle(Vector2(cloud_x, cloud_y), 24, Color(1, 1, 1, 0.23))
            draw_circle(Vector2(cloud_x + 27, cloud_y + 3), 19, Color(1, 1, 1, 0.21))
            draw_circle(Vector2(cloud_x - 24, cloud_y + 7), 17, Color(1, 1, 1, 0.18))

func _draw_landscape(viewport: Vector2, night: bool) -> void:
    var horizon := viewport.y * 0.51
    var far := Color("#183040") if night else Color("#6f917b")
    var mid := Color("#16342f") if night else Color("#4f7958")
    var ground := Color("#102b25") if night else Color("#345c3b")

    var far_hills := PackedVector2Array([Vector2(0, horizon + 45)])
    for i in range(9):
        far_hills.append(Vector2(float(i) * viewport.x / 8.0, horizon - 18.0 - sin(float(i) * 1.1) * 42.0))
    far_hills.append(Vector2(viewport.x, viewport.y))
    far_hills.append(Vector2(0, viewport.y))
    draw_colored_polygon(far_hills, far)

    var mid_hills := PackedVector2Array([Vector2(0, horizon + 80)])
    for i in range(8):
        mid_hills.append(Vector2(float(i) * viewport.x / 7.0, horizon + 25.0 - cos(float(i) * 1.32) * 34.0))
    mid_hills.append(Vector2(viewport.x, viewport.y))
    mid_hills.append(Vector2(0, viewport.y))
    draw_colored_polygon(mid_hills, mid)

    draw_rect(Rect2(0, horizon + 72, viewport.x, viewport.y - horizon - 72), ground)
    # foreground diorama lip
    draw_colored_polygon(PackedVector2Array([
        Vector2(0, viewport.y * 0.82), Vector2(viewport.x, viewport.y * 0.77),
        Vector2(viewport.x, viewport.y), Vector2(0, viewport.y)
    ]), Color("#0d211d") if night else Color("#294b33"))

func _draw_vignette(viewport: Vector2) -> void:
    var edge := 28.0
    draw_rect(Rect2(0, 0, viewport.x, edge), Color(0, 0, 0, 0.16))
    draw_rect(Rect2(0, viewport.y - edge, viewport.x, edge), Color(0, 0, 0, 0.24))
    draw_rect(Rect2(0, 0, edge, viewport.y), Color(0, 0, 0, 0.10))
    draw_rect(Rect2(viewport.x - edge, 0, edge, viewport.y), Color(0, 0, 0, 0.10))

func _connection_color() -> Color:
    if connection_state == "conectado": return Color("#75e6a5")
    if connection_state == "conectando": return Color("#ffd66b")
    return Color("#ff806f")

func _draw_brand(font: Font, viewport: Vector2) -> void:
    draw_circle(Vector2(42, 40), 13, Color(0.36, 0.84, 0.96, 0.16))
    draw_circle(Vector2(42, 40), 6, Color("#77d9ef"))
    draw_string(font, Vector2(64, 46), "LIVE INFINITA", HORIZONTAL_ALIGNMENT_LEFT, -1, 21, Color.WHITE)
    draw_string(font, Vector2(64, 65), "um mundo que continua", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color(0.82, 0.90, 0.93, 0.82))

    var live_rect := Rect2(viewport.x - 132, 25, 104, 34)
    draw_style_box(_panel_style(Color(0.35, 0.05, 0.08, 0.78), Color(1.0, 0.25, 0.34, 0.55)), live_rect)
    draw_circle(Vector2(live_rect.position.x + 17, live_rect.position.y + 17), 4.5, Color("#ff4055"))
    draw_string(font, Vector2(live_rect.position.x + 31, live_rect.position.y + 23), "AO VIVO", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color.WHITE)

func _draw_audience(font: Font, viewport: Vector2) -> void:
    if audience_feed.is_empty(): return
    var width := 285.0
    var height := 48.0 + audience_feed.size() * 23.0
    var rect := Rect2(viewport.x - width - 28, 82, width, height)
    _rounded_panel(rect, Color(0.76, 0.48, 0.76, 0.38), 0.54)
    draw_string(font, rect.position + Vector2(16, 25), "AGORA NA LIVE", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.93, 0.80, 0.94, 0.9))
    var y := rect.position.y + 49
    for i in range(audience_feed.size()):
        var alpha := 1.0 - float(i) * 0.12
        draw_circle(Vector2(rect.position.x + 18, y - 5), 3, Color(0.97, 0.63, 0.79, alpha))
        draw_string(font, Vector2(rect.position.x + 29, y), audience_feed[i], HORIZONTAL_ALIGNMENT_LEFT, width - 45, 13, Color(1, 1, 1, alpha))
        y += 23

func _draw_narration(font: Font, viewport: Vector2) -> void:
    var width := min(880.0, viewport.x - 180.0)
    var rect := Rect2((viewport.x - width) * 0.5, viewport.y - 116, width, 78)
    _rounded_panel(rect, Color(0.93, 0.72, 0.32, 0.42), 0.66)
    draw_string(font, rect.position + Vector2(20, 24), "NARRADOR", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color("#f5d47c"))
    draw_string(font, rect.position + Vector2(20, 53), narration_text, HORIZONTAL_ALIGNMENT_CENTER, rect.size.x - 40, 18, Color.WHITE)

func _draw_operator_status(font: Font, viewport: Vector2) -> void:
    # deliberately discreet: useful while developing, not the protagonist of the broadcast
    var rect := Rect2(28, viewport.y - 29, 430, 19)
    var status := "%s  ·  %s  ·  seq %s" % [connection_state, last_action, world.get("sequence", "-")]
    draw_circle(Vector2(rect.position.x + 5, rect.position.y + 7), 3.5, _connection_color())
    draw_string(font, Vector2(rect.position.x + 16, rect.position.y + 12), status, HORIZONTAL_ALIGNMENT_LEFT, rect.size.x - 16, 10, Color(0.86, 0.91, 0.92, 0.62))

func _draw() -> void:
    var viewport := get_viewport_rect().size
    var environment = world.get("environment", {})
    var period := "day"
    if typeof(environment) == TYPE_DICTIONARY:
        period = str(environment.get("period", "day"))
    var night := period == "night"

    _draw_sky(viewport, night)
    _draw_landscape(viewport, night)
    _draw_vignette(viewport)

    var font := ThemeDB.fallback_font
    _draw_brand(font, viewport)
    _draw_audience(font, viewport)
    _draw_narration(font, viewport)
    _draw_operator_status(font, viewport)
