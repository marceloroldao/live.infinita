extends Node2D

const EntityVisual = preload("res://entity_visual.gd")
const WS_RECONNECT_MAX_MS := 30000
const DIRECTOR_FOCUS_MS := 6500
const DIRECTOR_STAGE_CENTER := Vector2(360, 650)

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
var narration_text := ""
var narration_remaining := 0.0
var audience_remaining := 0.0
var night_amount := 0.0
var wind_amount := 0.25
var lighting_initialized := false
var camera_offset := Vector2.ZERO
var camera_target := Vector2.ZERO
var director_cooldown_until := 0
var sky_material := ShaderMaterial.new()
var retiring: Array[Node2D] = []
const MAX_RETIRING := 32
const MAX_CAMERA_SHIFT := 22.0
var ws_reconnect_attempt := 0
var ws_reconnect_at_ms := 0
var visual_time := 0.0
var director_focus_entity_id := ""
var director_focus_until_ms := 0

func _ready() -> void:
    var sky := ColorRect.new()
    sky.size = Vector2(720, 1280)
    sky.mouse_filter = Control.MOUSE_FILTER_IGNORE
    sky.z_index = -10
    sky_material.shader = preload("res://story_sky.gdshader")
    sky.material = sky_material
    add_child(sky)
    _connect_websocket()
    _install_browser_audio_bridge()
    queue_redraw()

func _install_browser_audio_bridge() -> void:
    if not OS.has_feature("web"): return
    var script := """
(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('capture') === '1') { window.__liveInfinitaCaptureMode = true; return true; }
  if (window.__liveInfinitaAudioInstalled) return true;
  window.__liveInfinitaAudioInstalled = true;
  const audio = document.createElement('audio');
  audio.id = 'live-infinita-program-audio'; audio.preload = 'none'; audio.src = '/audio/live.mp3'; audio.volume = 1.0;
  document.body.appendChild(audio);
  const btn = document.createElement('button');
  btn.id = 'live-infinita-audio-button'; btn.textContent = '🔊 ATIVAR ÁUDIO DA LIVE';
  Object.assign(btn.style, {position:'fixed',left:'50%',bottom:'18px',transform:'translateX(-50%)',zIndex:'99999',padding:'14px 22px',borderRadius:'12px',border:'1px solid rgba(255,255,255,.35)',background:'rgba(8,12,20,.92)',color:'#fff',font:'700 15px system-ui,sans-serif',cursor:'pointer'});
  document.body.appendChild(btn);
  const start = async () => { try { audio.src='/audio/live.mp3?ts='+Date.now(); await audio.play(); btn.textContent='🔊 ÁUDIO ATIVO'; setTimeout(()=>{btn.style.display='none';},1400); window.__liveInfinitaAudioActive=true; } catch(e) { btn.textContent='⚠ TOQUE NOVAMENTE'; } };
  btn.addEventListener('click', start);
  let reconnectTimer=null;
  const reconnect=()=>{ if(!window.__liveInfinitaAudioActive||reconnectTimer!==null)return; reconnectTimer=setTimeout(async()=>{reconnectTimer=null;try{audio.src='/audio/live.mp3?ts='+Date.now();await audio.play();}catch(_){reconnect();}},1200); };
  audio.addEventListener('ended',reconnect); audio.addEventListener('error',reconnect); return true;
})()
"""
    JavaScriptBridge.eval(script)

func _websocket_url() -> String:
    if OS.has_feature("web"):
        var protocol = JavaScriptBridge.eval("window.location.protocol")
        var host = JavaScriptBridge.eval("window.location.host")
        return ("wss://" if str(protocol) == "https:" else "ws://") + str(host) + "/ws"
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
    if ws_reconnect_at_ms != 0: return
    var exponent: int = mini(ws_reconnect_attempt, 5)
    var delay_ms: int = mini(WS_RECONNECT_MAX_MS, int(1000.0 * pow(2.0, float(exponent))))
    ws_reconnect_attempt += 1
    ws_reconnect_at_ms = Time.get_ticks_msec() + delay_ms
    queue_redraw()

func _maybe_reconnect_websocket() -> void:
    if ws_reconnect_at_ms == 0 or Time.get_ticks_msec() < ws_reconnect_at_ms: return
    ws_reconnect_at_ms = 0
    socket = WebSocketPeer.new()
    _connect_websocket()

func _process(delta: float) -> void:
    visual_time += delta
    narration_remaining = maxf(0.0, narration_remaining - delta)
    audience_remaining = maxf(0.0, audience_remaining - delta)
    _update_lighting(delta)
    socket.poll()
    var state := socket.get_ready_state()
    if state == WebSocketPeer.STATE_OPEN:
        if connection_state != "conectado":
            connection_state = "conectado"; ws_reconnect_attempt = 0; ws_reconnect_at_ms = 0
        while socket.get_available_packet_count() > 0:
            var parsed = JSON.parse_string(socket.get_packet().get_string_from_utf8())
            if typeof(parsed) != TYPE_DICTIONARY: continue
            var msg: Dictionary = parsed
            if str(msg.get("type", "")) == "world_state" and typeof(msg.get("world")) == TYPE_DICTIONARY: _apply_world_state(msg)
            elif str(msg.get("type", "")) == "audience_event" and typeof(msg.get("event")) == TYPE_DICTIONARY: _apply_audience_event(msg["event"])
    elif state == WebSocketPeer.STATE_CLOSED:
        if connection_state != "desconectado": connection_state = "desconectado"; _schedule_websocket_reconnect()
        _maybe_reconnect_websocket()
    else: _maybe_reconnect_websocket()
    _update_director_layout(delta)
    queue_redraw()

func _apply_world_state(message: Dictionary) -> void:
    world = Dictionary(message.get("world", {})).duplicate(true)
    last_reconcile = _reconcile_entities(world.get("entities", []))
    last_message = "World State v%s / seq %s" % [world.get("version", "?"), world.get("sequence", "?")]
    var event = message.get("event", {})
    if typeof(event) == TYPE_DICTIONARY:
        last_action = str(event.get("action", "evento do mundo")); last_event_id = str(event.get("event_id", "-"))
        _direct_from_event(event)
    var delta = message.get("delta", {})
    if typeof(delta) == TYPE_DICTIONARY: last_delta_id = str(delta.get("delta_id", "-"))
    var narration = world.get("narration", {})
    if typeof(narration) == TYPE_DICTIONARY:
        var text := str(narration.get("text", "")).strip_edges()
        if not text.is_empty() and text != narration_text:
            narration_text = text
            narration_remaining = clampf(float(text.length()) * 0.075, 8.0, 20.0)
    queue_redraw()

func _apply_audience_event(event: Dictionary) -> void:
    var kind := str(event.get("kind", "")).strip_edges().to_lower()
    var actor = event.get("actor", {})
    var name := "Visitante"
    if typeof(actor) == TYPE_DICTIONARY:
        var display := str(actor.get("display_name", "")).strip_edges()
        var actor_id := str(actor.get("actor_id", "")).strip_edges()
        name = display if not display.is_empty() else (actor_id if not actor_id.is_empty() else name)
    var line := "%s interagiu" % name
    match kind:
        "join": line = "%s entrou" % name
        "like": line = "%s curtiu" % name
        "gift": line = "%s enviou um presente" % name
    audience_remaining = 12.0
    audience_feed.push_front(line)
    while audience_feed.size() > 4: audience_feed.pop_back()
    queue_redraw()

func _reconcile_entities(entities) -> Dictionary:
    var result := {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}
    var seen: Dictionary = {}
    if typeof(entities) == TYPE_ARRAY:
        for entity in entities:
            if typeof(entity) != TYPE_DICTIONARY: continue
            var entity_id := str(entity.get("id", "")).strip_edges()
            if entity_id.is_empty(): continue
            seen[entity_id] = true
            if not entity_nodes.has(entity_id):
                var visual = EntityVisual.new(); visual.name = "Entity_%s" % entity_id; add_child(visual); entity_nodes[entity_id] = visual; visual.apply_entity(entity); result["added"] += 1
            else:
                if entity_nodes[entity_id].apply_entity(entity): result["updated"] += 1
                else: result["unchanged"] += 1
    for entity_id in entity_nodes.keys().duplicate():
        if not seen.has(entity_id):
            var visual = entity_nodes[entity_id]
            entity_nodes.erase(entity_id)
            _retire_visual(visual)
            result["removed"] += 1
    return result

func _first_entity_id_by_type(entity_type: String) -> String:
    var entities = world.get("entities", [])
    if typeof(entities) != TYPE_ARRAY: return ""
    for entity in entities:
        if typeof(entity) == TYPE_DICTIONARY and str(entity.get("type", "")) == entity_type:
            return str(entity.get("id", ""))
    return ""

func _last_entity_id_by_type(entity_type: String) -> String:
    var entities = world.get("entities", [])
    if typeof(entities) != TYPE_ARRAY: return ""
    for i in range(entities.size() - 1, -1, -1):
        var entity = entities[i]
        if typeof(entity) == TYPE_DICTIONARY and str(entity.get("type", "")) == entity_type:
            return str(entity.get("id", ""))
    return ""

func _direct_from_event(event: Dictionary) -> void:
    if Time.get_ticks_msec() < director_cooldown_until: return
    var action := str(event.get("action", ""))
    var next_focus := ""
    match action:
        "move_tree": next_focus = _first_entity_id_by_type("tree")
        "toggle_fire": next_focus = _first_entity_id_by_type("campfire")
        "spawn_person": next_focus = _last_entity_id_by_type("human")
        "move", "move_entity", "npc_move", "arrive": next_focus = str(event.get("entity_id", ""))
        _:
            if action == "reset": director_focus_entity_id = ""; director_focus_until_ms = 0
            return
    if next_focus.is_empty() or not entity_nodes.has(next_focus): return
    director_cooldown_until = Time.get_ticks_msec() + 14000
    director_focus_entity_id = next_focus
    director_focus_until_ms = Time.get_ticks_msec() + DIRECTOR_FOCUS_MS

func _update_lighting(delta: float) -> void:
    var environment: Dictionary = world.get("environment", {})
    var period := str(environment.get("period", "day"))
    var target := 1.0 if period == "night" else 0.0
    if period in ["dawn", "dusk", "twilight"]: target = 0.65
    if period in ["sunset", "sunrise"]: target = 0.35
    if not lighting_initialized and not world.is_empty():
        night_amount = target
        lighting_initialized = true
    night_amount = move_toward(night_amount, target, delta / 18.0)
    var weather := str(environment.get("weather", "clear"))
    var wind_target := 0.65 if weather in ["rain", "storm", "chuva"] else 0.25
    var wind_value = environment.get("wind", wind_target)
    if typeof(wind_value) in [TYPE_FLOAT, TYPE_INT]: wind_target = clampf(float(wind_value), 0.0, 1.0)
    wind_amount = lerpf(wind_amount, wind_target, 1.0 - exp(-delta * 0.5))
    sky_material.set_shader_parameter("night_amount", night_amount)
    sky_material.set_shader_parameter("dusk_amount", sin(night_amount * PI))

func _retire_visual(visual: Node2D) -> void:
    # Only a bounded, non-interactive presentation tail remains after hot eviction.
    for i in range(retiring.size() - 1, -1, -1):
        if not is_instance_valid(retiring[i]): retiring.remove_at(i)
    if retiring.size() >= MAX_RETIRING:
        var oldest: Node2D = retiring.pop_front()
        if is_instance_valid(oldest): oldest.queue_free()
    retiring.append(visual)
    visual.set_process(false)
    var fade := visual.create_tween()
    fade.tween_property(visual, "modulate:a", 0.0, 0.35)
    fade.tween_callback(visual.queue_free)

func _update_director_layout(delta: float = 0.016) -> void:
    var active := not director_focus_entity_id.is_empty() and Time.get_ticks_msec() < director_focus_until_ms and entity_nodes.has(director_focus_entity_id)
    camera_target = Vector2.ZERO
    if active:
        var focus = entity_nodes[director_focus_entity_id]
        camera_target = ((DIRECTOR_STAGE_CENTER - focus.position) * 0.10).limit_length(MAX_CAMERA_SHIFT)
    elif director_focus_until_ms != 0:
        director_focus_entity_id = ""
        director_focus_until_ms = 0
    camera_offset = camera_offset.move_toward(camera_target, delta * 4.0)
    for visual in entity_nodes.values():
        # Camera is a draw offset, never a walking waypoint.
        visual.camera_offset = camera_offset
        visual.night_amount = night_amount
        visual.wind_amount = wind_amount
        visual.restore_default_presentation(1.0)
        var foot_offset := 72.0 if visual.entity_type == "tree" else (49.0 if visual.entity_type == "human" else 25.0)
        visual.z_index = clampi(int(visual.position.y + foot_offset), 1, 2000)

func _draw_sky(v: Vector2, _night: bool) -> void:
    # Continuous shader below this node; celestial bodies cross-fade above it.
    for i in range(38):
        var x := fposmod(sin(float(i + 1) * 127.1) * 43758.5453, 1.0) * (v.x - 50.0) + 25.0
        var y := fposmod(sin(float(i + 1) * 311.7) * 19642.349, 1.0) * 340.0 + 105.0
        draw_circle(Vector2(x, y), 1.0 + float(i % 3) * 0.35, Color(0.94, 0.97, 1.0, night_amount * (0.48 + 0.16 * sin(visual_time * 0.7 + i))))
    var sun := Vector2(570, 220 + night_amount * 100)
    for i in range(8, 0, -1):
        draw_circle(sun, 34.0 + i * 8.0, Color(1.0, 0.79, 0.44, 0.015 * (1.0 - night_amount)))
    draw_circle(sun, 34, Color(1.0, 0.85, 0.56, 1.0 - night_amount))
    var moon := Vector2(565, 185)
    draw_circle(moon, 47, Color(0.81, 0.87, 1.0, 0.04 * night_amount))
    draw_circle(moon, 27, Color(0.94, 0.94, 0.81, night_amount))
    draw_circle(moon + Vector2(-7, 5), 6, Color(0.62, 0.69, 0.69, 0.18 * night_amount))
    for i in range(5):
        var cx := fmod(80.0 + i * 183.0 + visual_time * (2.0 + i * 0.5), v.x + 240.0) - 120.0
        var cy := 240.0 + i * 43.0
        var cloud := Color(0.96, 0.96, 0.86, lerpf(0.22, 0.055, night_amount))
        draw_set_transform(Vector2(cx, cy) + camera_offset * 0.06, 0.0, Vector2(1.8, 0.58))
        var contour := PackedVector2Array()
        for point in range(40):
            var angle := float(point) / 40.0 * TAU
            var radius := 1.0 + sin(angle * 5.0 + i) * 0.07
            contour.append(Vector2(cos(angle) * 54.0, sin(angle) * 24.0) * radius)
        draw_colored_polygon(contour, cloud)
        draw_set_transform(Vector2.ZERO)

func _draw() -> void:
    _draw_sky(Vector2(720, 1280), night_amount > 0.5)
