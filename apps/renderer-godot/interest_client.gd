extends Node

const UPDATE_INTERVAL_MS := 1200
const POSITION_EPSILON := 2.0

var observer_entity_id := ""
var last_position := Vector2.ZERO
var last_direction := Vector2.ZERO
var last_sent_at_ms := 0
var registered := false

func _process(_delta: float) -> void:
    var parent = get_parent()
    if parent == null:
        return
    var socket = parent.get("socket")
    if socket == null or socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
        registered = false
        return
    var world = parent.get("world")
    if typeof(world) != TYPE_DICTIONARY:
        return

    var observer := _resolve_observer(world)
    if observer.is_empty():
        return
    var entity_id := str(observer.get("id", ""))
    var position_data = observer.get("position", {})
    if entity_id.is_empty() or typeof(position_data) != TYPE_DICTIONARY:
        return
    var position := Vector2(float(position_data.get("x", 0.0)), float(position_data.get("y", 0.0)))

    var changed_observer := entity_id != observer_entity_id
    var displacement := position - last_position if registered and not changed_observer else Vector2.ZERO
    var moved := displacement.length() >= POSITION_EPSILON
    if moved:
        last_direction = displacement.normalized()

    var now := Time.get_ticks_msec()
    var due := now - last_sent_at_ms >= UPDATE_INTERVAL_MS
    if not registered or changed_observer or moved or due:
        observer_entity_id = entity_id
        last_position = position
        _send_interest_update(socket)
        registered = true
        last_sent_at_ms = now

func _resolve_observer(world: Dictionary) -> Dictionary:
    var entities = world.get("entities", [])
    if typeof(entities) != TYPE_ARRAY:
        return {}
    # Keep an already selected observer when it is still materialized.
    if not observer_entity_id.is_empty():
        for entity in entities:
            if typeof(entity) == TYPE_DICTIONARY and str(entity.get("id", "")) == observer_entity_id:
                return entity
    # Prefer an explicitly marked player/observer, then the first human.
    for entity in entities:
        if typeof(entity) != TYPE_DICTIONARY or str(entity.get("type", "")) != "human":
            continue
        var properties = entity.get("properties", {})
        if typeof(properties) == TYPE_DICTIONARY and bool(properties.get("observer", properties.get("player", false))):
            return entity
    for entity in entities:
        if typeof(entity) == TYPE_DICTIONARY and str(entity.get("type", "")) == "human":
            return entity
    return {}

func _send_interest_update(socket: WebSocketPeer) -> void:
    var payload := {
        "type": "interest_update",
        "observer_entity_id": observer_entity_id,
        "direction": {"x": last_direction.x, "y": last_direction.y},
    }
    socket.send_text(JSON.stringify(payload))
