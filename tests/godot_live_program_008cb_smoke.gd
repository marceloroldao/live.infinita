extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false)
    await process_frame
    var feed = stage.get_node("LiveFeed")
    feed.enabled = false
    feed.set_process(false)
    var overlay = stage._program_overlay
    overlay.set_process(false)
    check(not stage._hud._toggle.visible, "Exploration button must be hidden for live")
    feed._accept_packet(JSON.stringify({
        "type":"world_state", "world":{"narration":{"text":"NOV chegou ao abrigo."}}
    }))
    check(overlay._narration.visible, "Narration must be delivered even without spatial observer")
    check("NOV chegou ao abrigo." in overlay._narration.text, "Narrator caption must show source text")
    var before: float = overlay._narration_remaining
    feed._accept_packet(JSON.stringify({
        "type":"world_state", "world":{"narration":{"text":"NOV chegou ao abrigo."}}
    }))
    check(is_equal_approx(before, overlay._narration_remaining), "Repeated snapshot must not restart narration")
    feed._accept_packet(JSON.stringify({
        "type":"audience_event", "event":{"kind":"join","actor":{"display_name":"Roldão"}}
    }))
    check(overlay._audience.visible and "Roldão entrou" in overlay._audience.text,
        "Audience event must appear in live overlay")
    for i in range(8):
        feed._accept_packet(JSON.stringify({
            "type":"audience_event", "event":{"kind":"like","actor":{"display_name":"Visitante %d" % i}}
        }))
    check(overlay._audience_feed.size() == 4, "Audience list must remain bounded")
    overlay._process(21.0)
    check(not overlay._narration.visible and not overlay._audience.visible, "Stale captions must fade")
    stage.queue_free()
    await process_frame
    print("Live program smoke: ", failures, " failures")
    quit(1 if failures else 0)
