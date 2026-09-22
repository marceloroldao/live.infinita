extends Node

const FADE_SECONDS := 0.55
const START_ALPHA := 0.08
const START_SCALE_FACTOR := 0.96

var known_entities: Dictionary = {}
var active: Dictionary = {}
var promotions_total := 0
var predicted_promotions_total := 0

func _process(delta: float) -> void:
    var parent = get_parent()
    if parent == null:
        return
    var nodes = parent.get("entity_nodes")
    if typeof(nodes) != TYPE_DICTIONARY:
        return

    var warm_node = parent.get_node_or_null("WarmPrefetch")
    var warm_snapshot: Dictionary = {}
    if warm_node != null and warm_node.has_method("snapshot"):
        warm_snapshot = warm_node.snapshot()

    for entity_id in nodes.keys():
        if known_entities.has(entity_id):
            continue
        var visual = nodes[entity_id]
        if not is_instance_valid(visual):
            continue
        var predicted := warm_snapshot.has(entity_id)
        known_entities[entity_id] = true
        active[entity_id] = {
            "elapsed": 0.0,
            "predicted": predicted,
            "base_scale": visual.scale,
        }
        promotions_total += 1
        if predicted:
            predicted_promotions_total += 1
        visual.modulate.a = START_ALPHA
        visual.scale *= START_SCALE_FACTOR

    for entity_id in known_entities.keys().duplicate():
        if not nodes.has(entity_id):
            known_entities.erase(entity_id)
            active.erase(entity_id)

    for entity_id in active.keys().duplicate():
        if not nodes.has(entity_id):
            active.erase(entity_id)
            continue
        var visual = nodes[entity_id]
        if not is_instance_valid(visual):
            active.erase(entity_id)
            continue
        var state: Dictionary = active[entity_id]
        var elapsed := float(state.get("elapsed", 0.0)) + delta
        var t: float = clampf(elapsed / FADE_SECONDS, 0.0, 1.0)
        var eased: float = 1.0 - pow(1.0 - t, 3.0)
        visual.modulate.a = lerpf(START_ALPHA, 1.0, eased)
        # Do not fight the Smart Director after the short entry transition.
        if t < 1.0:
            var current_target := float(visual.get("target_presentation_scale"))
            var entry_scale := lerpf(current_target * START_SCALE_FACTOR, current_target, eased)
            visual.scale = Vector2.ONE * entry_scale
        state["elapsed"] = elapsed
        active[entity_id] = state
        if t >= 1.0:
            visual.modulate.a = 1.0
            active.erase(entity_id)

func metrics() -> Dictionary:
    return {
        "promotions_total": promotions_total,
        "predicted_promotions_total": predicted_promotions_total,
        "active_transitions": active.size(),
    }
