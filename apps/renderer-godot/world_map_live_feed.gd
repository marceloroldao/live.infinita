extends Node

signal world_slice_received(observer: Dictionary, current_region_id: String, hot_entities: Array, warm_entities: Array, region_descriptors: Array, sequence: int, cognitive_terrain: Dictionary, environmental_state: Dictionary)

signal sky_clock_received(clock: Dictionary)
signal memory_sky_received(projection: Dictionary)
signal physical_weather_received(weather: Dictionary)

signal navigation_context_received(context: Dictionary)

signal program_state_received(world: Dictionary)
signal audience_event_received(event: Dictionary)

const RECONNECT_MAX_MS := 12000
const WORLD_PACKET_BUFFER_BYTES := 2 * 1024 * 1024
var socket := WebSocketPeer.new()
var connection_state := "desconectado"
var reconnect_attempt := 0
var reconnect_at_ms := 0
var enabled := true

func _ready() -> void:
    for argument in OS.get_cmdline_user_args():
        if str(argument) == "--offline-tour":
            enabled = false
    if enabled:
        _connect()

func _websocket_url() -> String:
    if OS.has_feature("web"):
        var protocol = JavaScriptBridge.eval("window.location.protocol")
        var host = JavaScriptBridge.eval("window.location.host")
        return ("wss://" if str(protocol) == "https:" else "ws://") + str(host) + "/ws"
    return "ws://127.0.0.1:8080/ws"

func _connect() -> void:
    # Terrain and environmental slices exceed the default 64 KiB buffer.
    # Configure every new peer, including reconnects, before the handshake.
    socket.inbound_buffer_size = WORLD_PACKET_BUFFER_BYTES
    connection_state = "conectando"
    var err := socket.connect_to_url(_websocket_url())
    if err != OK:
        connection_state = "erro"
        _schedule_reconnect()

func _schedule_reconnect() -> void:
    if reconnect_at_ms != 0:
        return
    var exponent := mini(reconnect_attempt, 4)
    var delay_ms := mini(RECONNECT_MAX_MS, int(1000.0 * pow(2.0, float(exponent))))
    reconnect_attempt += 1
    reconnect_at_ms = Time.get_ticks_msec() + delay_ms

func _maybe_reconnect() -> void:
    if reconnect_at_ms == 0 or Time.get_ticks_msec() < reconnect_at_ms:
        return
    reconnect_at_ms = 0
    socket = WebSocketPeer.new()
    _connect()

func _process(_delta: float) -> void:
    if not enabled:
        return
    socket.poll()
    var state := socket.get_ready_state()
    if state == WebSocketPeer.STATE_OPEN:
        if connection_state != "conectado":
            connection_state = "conectado"
            reconnect_attempt = 0
            reconnect_at_ms = 0
        while socket.get_available_packet_count() > 0:
            _accept_packet(socket.get_packet().get_string_from_utf8())
    elif state == WebSocketPeer.STATE_CLOSED:
        if connection_state != "desconectado":
            connection_state = "desconectado"
            _schedule_reconnect()
        _maybe_reconnect()
    else:
        _maybe_reconnect()

func _accept_packet(raw: String) -> void:
    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    var message: Dictionary = parsed
    if str(message.get("type", "")) == "audience_event":
        var event = message.get("event", {})
        if typeof(event) == TYPE_DICTIONARY:
            audience_event_received.emit(Dictionary(event).duplicate(true))
        return
    if str(message.get("type", "")) != "world_state":
        return
    var program_world = message.get("world", {})
    if typeof(program_world) == TYPE_DICTIONARY:
        program_state_received.emit(Dictionary(program_world).duplicate(true))
    var delivery = message.get("delivery", {})
    var world = message.get("world", {})
    if typeof(delivery) != TYPE_DICTIONARY or typeof(world) != TYPE_DICTIONARY:
        return
    var observer = delivery.get("observer", {})
    var interest = world.get("interest", {})
    if typeof(observer) != TYPE_DICTIONARY or typeof(interest) != TYPE_DICTIONARY:
        return
    var hot = world.get("entities", [])
    var warm = interest.get("warm_entities", [])
    var regions = interest.get("region_descriptors", [])
    if typeof(hot) != TYPE_ARRAY or typeof(warm) != TYPE_ARRAY or typeof(regions) != TYPE_ARRAY:
        return
    var cognitive_terrain = delivery.get("cognitive_terrain", {})
    if typeof(cognitive_terrain) != TYPE_DICTIONARY:
        cognitive_terrain = {}
    var environmental_state = delivery.get("environmental_state", {})
    if typeof(environmental_state) != TYPE_DICTIONARY:
        environmental_state = {}
    var weather = delivery.get("physical_weather", {})
    if typeof(weather) == TYPE_DICTIONARY and str(weather.get("world_id","")) == str(world.get("world_id","")):
        physical_weather_received.emit(Dictionary(weather).duplicate(true))
    var memory_sky = delivery.get("memory_sky", {})
    if typeof(memory_sky) == TYPE_DICTIONARY and str(memory_sky.get("world_id", "")) == str(world.get("world_id", "")):
        memory_sky_received.emit(Dictionary(memory_sky).duplicate(true))
    var sky_clock = delivery.get("sky_clock", {})
    if typeof(sky_clock) == TYPE_DICTIONARY and str(sky_clock.get("world_id", "")) == str(world.get("world_id", "")):
        sky_clock_received.emit(Dictionary(sky_clock).duplicate(true))
    var observer_position = observer.get("position", observer)
    navigation_context_received.emit({
        "world_id": str(world.get("world_id", "")), "world_sequence": int(world.get("sequence", -1)),
        "observer_entity_id": str(delivery.get("observer_entity_id", "")),
        "runtime_position": Dictionary(observer_position).duplicate(true) if typeof(observer_position) == TYPE_DICTIONARY else {},
        "region_id": str(interest.get("current_region_id", "")),
    })
    world_slice_received.emit(
        Dictionary(observer).duplicate(true),
        str(interest.get("current_region_id", "")),
        Array(hot).duplicate(true),
        Array(warm).duplicate(true),
        Array(regions).duplicate(true),
        int(world.get("sequence", -1)),
        Dictionary(cognitive_terrain).duplicate(true),
        Dictionary(environmental_state).duplicate(true),
    )
