extends Node

const MAX_WARM_CACHE := 192
const MAX_AGE_MS := 12000

var warm_cache: Dictionary = {}
var last_sequence := -1

func _process(_delta: float) -> void:
    var parent = get_parent()
    if parent == null:
        return
    var world = parent.get("world")
    if typeof(world) != TYPE_DICTIONARY:
        return
    var sequence := int(world.get("sequence", -1))
    if sequence == last_sequence:
        _evict_expired()
        return
    last_sequence = sequence
    _ingest_world(world)
    _evict_expired()

func _ingest_world(world: Dictionary) -> void:
    var interest = world.get("interest", {})
    if typeof(interest) != TYPE_DICTIONARY:
        return
    var warm_entities = interest.get("warm_entities", [])
    if typeof(warm_entities) != TYPE_ARRAY:
        return

    var now := Time.get_ticks_msec()
    for entity in warm_entities:
        if typeof(entity) != TYPE_DICTIONARY:
            continue
        var entity_id := str(entity.get("id", "")).strip_edges()
        if entity_id.is_empty():
            continue
        warm_cache[entity_id] = {
            "id": entity_id,
            "type": str(entity.get("type", "")),
            "position": Dictionary(entity.get("position", {})).duplicate(true),
            "seen_at_ms": now,
            "sequence": int(world.get("sequence", -1)),
        }

    var hot_ids: Dictionary = {}
    var hot_entities = world.get("entities", [])
    if typeof(hot_entities) == TYPE_ARRAY:
        for entity in hot_entities:
            if typeof(entity) == TYPE_DICTIONARY:
                var hot_id := str(entity.get("id", "")).strip_edges()
                if not hot_id.is_empty():
                    hot_ids[hot_id] = true
    for entity_id in hot_ids.keys():
        warm_cache.erase(entity_id)

    _trim_cache()

func _trim_cache() -> void:
    if warm_cache.size() <= MAX_WARM_CACHE:
        return
    var rows: Array = []
    for entity_id in warm_cache.keys():
        var row: Dictionary = warm_cache[entity_id]
        rows.append({"id": entity_id, "seen_at_ms": int(row.get("seen_at_ms", 0))})
    rows.sort_custom(func(a, b): return int(a["seen_at_ms"]) < int(b["seen_at_ms"]))
    while warm_cache.size() > MAX_WARM_CACHE and not rows.is_empty():
        var oldest = rows.pop_front()
        warm_cache.erase(oldest["id"])

func _evict_expired() -> void:
    var now := Time.get_ticks_msec()
    for entity_id in warm_cache.keys().duplicate():
        var row: Dictionary = warm_cache[entity_id]
        if now - int(row.get("seen_at_ms", 0)) > MAX_AGE_MS:
            warm_cache.erase(entity_id)

func snapshot() -> Dictionary:
    return warm_cache.duplicate(true)
