extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var feed = load("res://nov_animal_search_panel.gd").new()
    root.add_child(feed)
    feed.set_process(false)
    feed.enabled = true
    feed.set_world("fixture")
    var now := Time.get_unix_time_from_system()
    var memory := {"schema":feed.MEMORY_SCHEMA,"world_id":"fixture","generated_at_unix":now,
        "world_write_authority":false,"decision_use":false,"last_error":null,"stored_and_recovered_encounters":12}
    var prediction := {"schema":feed.SEARCH_SCHEMA,"world_id":"fixture","generated_at_unix":now,
        "source":"verified_recalled_eye_encounters","world_write_authority":false,"decision_use":false,
        "last_error":null,"contains_prediction":true,"absence_claim":false,"logical_time_ms":100000,
        "counters":{"issued":3,"paired":0,"memory_hits":0,"last_seen_hits":0,"expired_without_observation":0},
        "forecasts":[{"issued_ms":99000,"expires_ms":159000,"contains_prediction":true},
                     {"issued_ms":99000,"expires_ms":159000,"contains_prediction":true},
                     {"issued_ms":99000,"expires_ms":159000,"contains_prediction":true}]}
    check(feed._accept(JSON.stringify(memory),"memory"),"Valid recovered encounter counters must be accepted")
    check(feed._accept(JSON.stringify(prediction),"search"),"Valid independent forecast status must be accepted")
    check("12 lembrados" in feed.lines(now) and "3 regiões" in feed.lines(now),"Panel uses remembered encounter and active region counts")
    check("novo avistamento" in feed.lines(now) and not "0/0" in feed.lines(now),"No measured pairs must show pending observation, not fabricated precision")
    var damaged: Dictionary = prediction.duplicate(true)
    damaged.world_id = "other"
    check(not feed._accept(JSON.stringify(damaged),"search"),"Cross-world counts must be rejected")
    damaged = prediction.duplicate(true)
    damaged.generated_at_unix = now-61
    check(not feed._accept(JSON.stringify(damaged),"search"),"Stale forecast cannot replace fresh panel")
    check(not "3 regiões" in feed.lines(now+61),"Expired cached data must not remain presented as live")
    damaged.generated_at_unix = now+31
    check(not feed._accept(JSON.stringify(damaged),"search"),"Future wall-clock publication must be rejected")
    damaged = prediction.duplicate(true)
    damaged.generated_at_unix = now-1
    damaged.counters.issued = 2
    check(not feed._accept(JSON.stringify(damaged),"search"),"Delayed status cannot overwrite a newer snapshot")
    damaged = prediction.duplicate(true)
    damaged.counters.memory_hits = 1
    check(not feed._accept(JSON.stringify(damaged),"search"),"Hits cannot exceed measured comparisons")
    damaged = prediction.duplicate(true)
    damaged.counters.issued = -1
    check(not feed._accept(JSON.stringify(damaged),"search"),"Negative counters must not be rendered")
    damaged = prediction.duplicate(true)
    damaged.counters.paired = 0.5
    check(not feed._accept(JSON.stringify(damaged),"search"),"Fractional comparisons must be rejected")
    damaged = prediction.duplicate(true)
    damaged.forecasts[0].issued_ms = 100001
    check(not feed._accept(JSON.stringify(damaged),"search"),"Future-issued logical forecasts cannot be shown")
    damaged = prediction.duplicate(true)
    damaged.forecasts[0].contains_prediction = false
    check(not feed._accept(JSON.stringify(damaged),"search"),"Forecasts must remain distinct from observations")
    damaged = prediction.duplicate(true)
    damaged.last_error = "animal_search_inputs_unavailable"
    check(not feed._accept(JSON.stringify(damaged),"search"),"Failed predictor cannot publish ordinary counters")
    damaged = prediction.duplicate(true)
    damaged.decision_use = true
    check(not feed._accept(JSON.stringify(damaged),"search"),"Shadow panel cannot claim active decision control")
    check(not feed._accept("[".repeat(131073),"search"),"Oversized response must be rejected")
    prediction.logical_time_ms = 160000
    prediction.generated_at_unix = now+1
    check(feed._accept(JSON.stringify(prediction),"search"),"Elapsed forecasts can await delayed ACK")
    check("0 regiões" in feed.lines(now+1) and "aguardando confirmação" in feed.lines(now+1),"Expired forecasts must not count as active predictions")
    prediction.forecasts = []
    prediction.counters = {"issued":3,"paired":2,"memory_hits":1,"last_seen_hits":2,"expired_without_observation":1}
    prediction.generated_at_unix = now+2
    check(feed._accept(JSON.stringify(prediction),"search"),"Paired empirical comparison must be accepted")
    check("memória 1/2" in feed.lines(now+2) and "último 2/2" in feed.lines(now+2),"Panel must show both actual comparison counts even when memory loses")
    check(feed.web_url("/godot/wildlife/search-predictions.json","https://live.etbra.com.br/")=="https://live.etbra.com.br/godot/wildlife/search-predictions.json","Web requests require absolute current-origin URLs")
    check(feed.web_url("/status","null").is_empty(),"Invalid origin must never cause relative web request")
    feed.set_world("new-world")
    check("12 lembrados" not in feed.lines(now+2),"World switch must clear both prior caches")
    feed.enabled = false
    check(feed.lines()=="Animais: prévia offline","Offline scene cannot claim server experiments")
    check(not feed._accept(JSON.stringify(memory),"memory"),"Offline node cannot accept live counters")
    var hud = load("res://world_map_hud.gd").new()
    root.add_child(hud)
    await process_frame
    hud._animal_search.set_process(false)
    hud._animal_search.enabled = true
    hud.set_animal_world("fixture")
    hud._animal_search._accept(JSON.stringify(memory),"memory")
    hud._animal_search._accept(JSON.stringify(prediction),"search")
    var experience = load("res://nov_navigation_experience.gd").new("")
    var journey = load("res://nov_navigation_journey.gd").new(experience.working_memory)
    hud.update_learning(experience,journey)
    check("12 lembrados" in hud._learning.text and "memória 1/2" in hud._learning.text,"Existing live panel must include independent animal results")
    check("RAM" in hud._learning.text and "Retornos ao início" in hud._learning.text,"Existing walking counters must remain visible")
    check(not hud._toggle.visible,"Exploration must remain hidden")
    check(hud._learning.get_theme_font_size("font_size")==15,"Combined panel keeps compact broadcast type size")
    var width := ThemeDB.fallback_font.get_string_size("Animais: 12 lembrados | 3 regiões",HORIZONTAL_ALIGNMENT_LEFT,-1,15).x
    check(width <= 288,"Animal summary must fit existing panel content width")
    for argument in OS.get_cmdline_user_args():
        if str(argument).begins_with("--animal-panel-http="):
            var origin := str(argument).trim_prefix("--animal-panel-http=")
            feed.enabled = true
            feed.set_world("fixture")
            for kind in ["memory","search"]:
                var filename := "encounter-memory.json" if kind=="memory" else "search-predictions.json"
                var request := HTTPRequest.new()
                request.timeout = 4.0
                root.add_child(request)
                request.request_completed.connect(Callable(feed,"_on_response").bind(kind))
                check(request.request(feed.web_url("/godot/wildlife/"+filename,origin))==OK,"Real HTTP request must start")
                var deadline := Time.get_ticks_msec()+6000
                while (feed._memory.is_empty() if kind=="memory" else feed._search.is_empty()) and Time.get_ticks_msec()<deadline:
                    await process_frame
                check(not (feed._memory.is_empty() if kind=="memory" else feed._search.is_empty()),"Real HTTP response must reach presentation cache")
                request.queue_free()
    hud.queue_free()
    feed.queue_free()
    await process_frame
    print("Animal search panel smoke: ",failures," failures")
    quit(1 if failures else 0)
