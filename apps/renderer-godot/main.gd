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
var narration_text := "A Live Infinita está começando."
var ws_reconnect_attempt := 0
var ws_reconnect_at_ms := 0
var visual_time := 0.0
var director_focus_entity_id := ""
var director_focus_until_ms := 0

func _ready() -> void:
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
    _update_director_layout()
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
        if not text.is_empty(): narration_text = text
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
            var visual = entity_nodes[entity_id]; entity_nodes.erase(entity_id); visual.queue_free(); result["removed"] += 1
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
    var action := str(event.get("action", ""))
    var next_focus := ""
    match action:
        "move_tree": next_focus = _first_entity_id_by_type("tree")
        "toggle_fire": next_focus = _first_entity_id_by_type("campfire")
        "spawn_person": next_focus = _last_entity_id_by_type("human")
        _:
            if action == "reset": director_focus_entity_id = ""; director_focus_until_ms = 0
            return
    if next_focus.is_empty() or not entity_nodes.has(next_focus): return
    director_focus_entity_id = next_focus
    director_focus_until_ms = Time.get_ticks_msec() + DIRECTOR_FOCUS_MS

func _update_director_layout() -> void:
    var active := not director_focus_entity_id.is_empty() and Time.get_ticks_msec() < director_focus_until_ms and entity_nodes.has(director_focus_entity_id)
    if not active:
        if director_focus_until_ms != 0 and Time.get_ticks_msec() >= director_focus_until_ms:
            director_focus_entity_id = ""; director_focus_until_ms = 0
        for visual in entity_nodes.values(): visual.restore_default_presentation(1.0)
        return
    var focus = entity_nodes[director_focus_entity_id]
    var focus_default: Vector2 = focus.world_to_portrait(focus.world_position)
    var camera_shift := (DIRECTOR_STAGE_CENTER - focus_default) * 0.18
    for entity_id in entity_nodes.keys():
        var visual = entity_nodes[entity_id]
        var base: Vector2 = visual.world_to_portrait(visual.world_position)
        var emphasis := 1.16 if entity_id == director_focus_entity_id else 0.94
        visual.set_presentation_target(base + camera_shift, emphasis)

func _panel_style(fill: Color, border: Color, radius: int = 18) -> StyleBoxFlat:
    var style := StyleBoxFlat.new(); style.bg_color = fill; style.border_color = border; style.set_border_width_all(1)
    style.corner_radius_top_left = radius; style.corner_radius_top_right = radius; style.corner_radius_bottom_left = radius; style.corner_radius_bottom_right = radius
    style.shadow_color = Color(0,0,0,0.24); style.shadow_size = 12
    return style

func _draw_sky(v: Vector2, night: bool) -> void:
    var top := Color("#071421") if night else Color("#67afd5")
    var bottom := Color("#315066") if night else Color("#dce9d6")
    for i in range(16):
        var t := float(i)/15.0
        draw_rect(Rect2(0, v.y*t*0.62, v.x, v.y*0.62/16.0+2), top.lerp(bottom,t))
    if night:
        for i in range(32):
            var x := fmod(float(i*149+61),v.x-50.0)+25.0; var y := fmod(float(i*83+29),v.y*0.42)+30.0
            draw_circle(Vector2(x,y),1.0+float(i%3)*0.35,Color(0.94,0.97,1.0,0.48+0.35*sin(visual_time*1.6+i)))
        draw_circle(Vector2(v.x-90,150),44,Color(0.95,0.94,0.79,0.10)); draw_circle(Vector2(v.x-90,150),31,Color("#f2edc8"))
    else:
        draw_circle(Vector2(v.x-90,150),62,Color(1.0,0.77,0.30,0.10)); draw_circle(Vector2(v.x-90,150),36,Color("#f8c75e"))
        for i in range(3):
            var cx := fmod(80.0+i*270.0+visual_time*(4.0+i),v.x+180.0)-90.0; var cy := 190.0+i*75.0
            draw_circle(Vector2(cx,cy),26,Color(1,1,1,0.22)); draw_circle(Vector2(cx+28,cy+3),20,Color(1,1,1,0.20)); draw_circle(Vector2(cx-25,cy+8),18,Color(1,1,1,0.17))

func _draw_landscape(v: Vector2, night: bool) -> void:
    var horizon := v.y*0.49
    var far := Color("#183040") if night else Color("#75977f"); var mid := Color("#16342f") if night else Color("#527c59"); var ground := Color("#102b25") if night else Color("#365f3e")
    var hills := PackedVector2Array([Vector2(0,horizon+55)])
    for i in range(7): hills.append(Vector2(float(i)*v.x/6.0,horizon-20.0-sin(float(i)*1.13)*54.0))
    hills.append(Vector2(v.x,v.y)); hills.append(Vector2(0,v.y)); draw_colored_polygon(hills,far)
    var hills2 := PackedVector2Array([Vector2(0,horizon+105)])
    for i in range(7): hills2.append(Vector2(float(i)*v.x/6.0,horizon+35.0-cos(float(i)*1.27)*42.0))
    hills2.append(Vector2(v.x,v.y)); hills2.append(Vector2(0,v.y)); draw_colored_polygon(hills2,mid)
    draw_rect(Rect2(0,horizon+105,v.x,v.y-horizon-105),ground)
    draw_colored_polygon(PackedVector2Array([Vector2(0,v.y*0.83),Vector2(v.x,v.y*0.79),Vector2(v.x,v.y),Vector2(0,v.y)]),Color("#0d211d") if night else Color("#294b33"))

func _draw_brand(font: Font, v: Vector2) -> void:
    draw_circle(Vector2(46,52),15,Color(0.36,0.84,0.96,0.16)); draw_circle(Vector2(46,52),7,Color("#77d9ef"))
    draw_string(font,Vector2(72,57),"LIVE INFINITA",HORIZONTAL_ALIGNMENT_LEFT,-1,22,Color.WHITE)
    draw_string(font,Vector2(72,78),"um mundo que continua",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color(0.84,0.91,0.94,0.82))
    var r := Rect2(v.x-126,34,96,34); draw_style_box(_panel_style(Color(0.35,0.05,0.08,0.82),Color(1,0.25,0.34,0.55),14),r)
    draw_circle(Vector2(r.position.x+16,r.position.y+17),4.5,Color("#ff4055")); draw_string(font,r.position+Vector2(29,23),"AO VIVO",HORIZONTAL_ALIGNMENT_LEFT,-1,13,Color.WHITE)

func _draw_audience(font: Font, v: Vector2) -> void:
    if audience_feed.is_empty(): return
    var width := v.x-60.0; var height := 48.0+audience_feed.size()*25.0; var r := Rect2(30,102,width,height)
    draw_style_box(_panel_style(Color(0.025,0.045,0.07,0.48),Color(0.76,0.48,0.76,0.34)),r)
    draw_string(font,r.position+Vector2(18,26),"AGORA NA LIVE",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color(0.95,0.80,0.95,0.9))
    var y := r.position.y+53
    for i in range(audience_feed.size()):
        var alpha := 1.0-float(i)*0.14; draw_circle(Vector2(r.position.x+20,y-5),3.5,Color(0.97,0.63,0.79,alpha)); draw_string(font,Vector2(r.position.x+33,y),audience_feed[i],HORIZONTAL_ALIGNMENT_LEFT,width-52,14,Color(1,1,1,alpha)); y += 25

func _draw_narration(font: Font, v: Vector2) -> void:
    var r := Rect2(30,v.y-196,v.x-60,128)
    draw_style_box(_panel_style(Color(0.02,0.04,0.06,0.72),Color(0.93,0.72,0.32,0.40)),r)
    draw_string(font,r.position+Vector2(20,28),"NARRADOR",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color("#f5d47c"))
    draw_multiline_string(font,r.position+Vector2(20,59),narration_text,HORIZONTAL_ALIGNMENT_CENTER,r.size.x-40,20,-1,Color.WHITE)

func _draw_safe_guides(v: Vector2) -> void:
    if not OS.has_feature("web"): return
    var guides = JavaScriptBridge.eval("new URLSearchParams(window.location.search).get('guides')")
    if str(guides) != "1": return
    draw_rect(Rect2(24,24,v.x-48,v.y-48),Color(1,1,1,0.22),false,1)
    draw_rect(Rect2(24,96,v.x-48,v.y-250),Color(1,0.75,0.25,0.30),false,1)

func _draw() -> void:
    var v := get_viewport_rect().size
    var environment = world.get("environment", {}); var period := "day"
    if typeof(environment) == TYPE_DICTIONARY: period = str(environment.get("period","day"))
    var night := period == "night"
    _draw_sky(v,night); _draw_landscape(v,night)
    draw_rect(Rect2(0,0,v.x,28),Color(0,0,0,0.15)); draw_rect(Rect2(0,v.y-34,v.x,34),Color(0,0,0,0.24)); draw_rect(Rect2(0,0,20,v.y),Color(0,0,0,0.10)); draw_rect(Rect2(v.x-20,0,20,v.y),Color(0,0,0,0.10))
    var font := ThemeDB.fallback_font
    _draw_brand(font,v); _draw_audience(font,v); _draw_narration(font,v); _draw_safe_guides(v)
