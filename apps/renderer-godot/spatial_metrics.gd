extends Node

const EMIT_INTERVAL_MS := 1000
var last_emit_ms := 0

func _process(_delta: float) -> void:
    if not OS.has_feature("web"):
        return
    var now := Time.get_ticks_msec()
    if now - last_emit_ms < EMIT_INTERVAL_MS:
        return
    last_emit_ms = now
    _emit_metrics()

func _emit_metrics() -> void:
    var parent = get_parent()
    if parent == null:
        return
    var world = parent.get("world")
    if typeof(world) != TYPE_DICTIONARY:
        return

    var hot_count := 0
    var hot_entities = world.get("entities", [])
    if typeof(hot_entities) == TYPE_ARRAY:
        hot_count = hot_entities.size()

    var warm_count := 0
    var interest = world.get("interest", {})
    if typeof(interest) == TYPE_DICTIONARY:
        var warm = interest.get("warm_entities", [])
        if typeof(warm) == TYPE_ARRAY:
            warm_count = warm.size()

    var transition_metrics := {
        "promotions_total": 0,
        "predicted_promotions_total": 0,
        "active_transitions": 0,
    }
    var transition = parent.get_node_or_null("MaterializationTransition")
    if transition != null and transition.has_method("metrics"):
        transition_metrics = transition.metrics()

    var promotions := int(transition_metrics.get("promotions_total", 0))
    var predicted := int(transition_metrics.get("predicted_promotions_total", 0))
    var unexpected := max(0, promotions - predicted)
    var hit_rate := 0.0
    if promotions > 0:
        hit_rate = float(predicted) / float(promotions)

    var payload := {
        "type": "live-infinita-spatial-metrics",
        "hot": hot_count,
        "warm": warm_count,
        "cold_omitted": bool(interest.get("cold_omitted", false)) if typeof(interest) == TYPE_DICTIONARY else false,
        "promotions_total": promotions,
        "predicted_promotions_total": predicted,
        "unexpected_promotions_total": unexpected,
        "prefetch_hit_rate": hit_rate,
        "active_transitions": int(transition_metrics.get("active_transitions", 0)),
    }
    var json := JSON.stringify(payload)
    JavaScriptBridge.eval("window.parent.postMessage(%s, window.location.origin)" % json)
