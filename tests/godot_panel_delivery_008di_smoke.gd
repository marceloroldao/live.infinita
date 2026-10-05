extends SceneTree
var failures := 0
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var feed = load("res://nov_navigation_recall.gd").new()
    root.add_child(feed)
    feed.enabled = false
    var experience = load("res://nov_navigation_experience.gd").new("")
    feed.learning_status_ready.connect(Callable(experience,"apply_learning_status"))
    feed.snapshot_ready.connect(Callable(experience,"apply_recall"))
    check(feed.web_url("/godot/navigation-memory/recall.json","https://live.etbra.com.br")=="https://live.etbra.com.br/godot/navigation-memory/recall.json","Recall requires absolute same-origin URL")
    check(feed.web_url("/godot/navigation-memory/status.json","http://127.0.0.1:8080/")=="http://127.0.0.1:8080/godot/navigation-memory/status.json","Panel URL must use current origin and port")
    check(feed.web_url("/status","null").is_empty(),"Invalid origin cannot produce a relative request")
    var now := Time.get_unix_time_from_system()
    var status := {"world_id":"fixture","observed_at_unix":now,"completed_steps":27,"causal_ram_steps":3}
    var envelope := {"schema":"live-infinita-nov-panel/v1","source":"native_renderer_journey","world_id":"fixture","generated_at_unix":now,"learning_status":status}
    feed._accept_status(JSON.stringify(envelope))
    check(experience.server_learning_status.get("completed_steps",0)==27,"Independent panel must receive actual counters")
    experience.apply_recall({})
    check(experience.server_learning_status.get("completed_steps",0)==27,"Recall expiration must not clear fresh independent counters")
    experience.apply_recall({"learning_status":{"observed_at_unix":now-10,"completed_steps":9},"entries":[]})
    check(experience.server_learning_status.get("completed_steps",0)==27,"Delayed recall must not replace newer panel")
    envelope["generated_at_unix"]=now-120
    envelope["learning_status"]={"completed_steps":99}
    feed._accept_status(JSON.stringify(envelope))
    check(experience.server_learning_status.get("completed_steps",0)==27,"Stale delivery cannot replace current counters")
    envelope["generated_at_unix"]=now
    envelope["learning_status"]={}
    feed._accept_status(JSON.stringify(envelope))
    check(experience.server_learning_status.is_empty(),"Unavailable native source must clear panel without inventing counts")
    for argument in OS.get_cmdline_user_args():
        if str(argument).begins_with("--panel-http="):
            var endpoint := str(argument).trim_prefix("--panel-http=")
            var request := HTTPRequest.new()
            request.timeout = 4.0
            root.add_child(request)
            request.request_completed.connect(Callable(feed,"_on_status_response"))
            check(request.request(feed.web_url("/godot/navigation-memory/status.json",endpoint))==OK,"Real HTTP request must accept absolute URL")
            var deadline := Time.get_ticks_msec()+6000
            while experience.server_learning_status.is_empty() and Time.get_ticks_msec()<deadline:
                await process_frame
            check(experience.server_learning_status.get("completed_steps",0)==27,"Real HTTP response must reach panel consumer")
            request.queue_free()
    feed.queue_free()
    await process_frame
    print("Panel delivery smoke: ",failures," failures")
    quit(1 if failures else 0)
