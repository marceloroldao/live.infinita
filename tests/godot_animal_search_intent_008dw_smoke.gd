extends SceneTree
var failures := 0
var directory := ""
var now := 100000
var session := "a".repeat(32)
func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures+=1
func _initialize() -> void:
    call_deferred("run")
func source(stamp: int, point: Array = [8,0]) -> void:
    var value := {"schema":"live-infinita-nov-animal-search/v1","world_id":"fixture","session_id":session,
        "logical_time_ms":stamp,"pending":[{"entity_id":"fixture:rabbit:0","issued_ms":stamp-1000,
        "expires_ms":stamp+59000,"forecast_id":"b".repeat(64),"center_xz_m":point,
        "last_seen_xz_m":[12,0],"contains_prediction":true,"radius_m":8,
        "evidence_ids":["structural-event:"+ "1".repeat(40),"structural-event:"+ "2".repeat(40),"structural-event:"+ "3".repeat(40)]}]}
    var raw := JSON.stringify(value)
    var f := FileAccess.open(directory+"/forecast",FileAccess.WRITE)
    f.store_string(JSON.stringify({"payload":raw,"sha256":raw.sha256_text()}));f.close()
func policy(name: String = "policy") -> RefCounted:
    var value = load("res://nov_animal_search_intent.gd").new()
    value.configure(directory+"/"+name,directory+"/"+name+".public",directory+"/forecast",session)
    return value
func allowed(point: Vector3) -> Dictionary:
    return {"allowed":true,"position":point}
func run() -> void:
    directory="/tmp/nov-animal-search-"+Crypto.new().generate_random_bytes(8).hex_encode()
    DirAccess.make_dir_recursive_absolute(directory)
    source(now)
    var value = policy()
    check(value.choose(Vector3.ZERO,"fixture",now,false,Callable(self,"allowed")).is_empty(),"Ordinary journey cannot be preempted")
    check(value._serial==0,"Waiting for normal journey must not consume search quota")
    var selected: Dictionary = value.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"))
    check(selected.get("arm")=="memory" and selected.goal==[8.0,0.0,0.0],"First search must use recalled recurrence region")
    check(selected.evidence_ids.size()==3,"Search must retain actual recalled evidence identities")
    check(value._counts.memory.started==1,"One active search must consume exactly one quota")
    for i in range(10):value.choose(Vector3.ZERO,"fixture",now+i,true,Callable(self,"allowed"))
    check(value._counts.memory.started==1,"Repeated frames cannot reissue active intent")
    var blocked = policy("blocked")
    check(blocked.choose(Vector3.ZERO,"fixture",now,true,func(_p:Vector3)->Dictionary:return {"allowed":false}).is_empty(),"Unwalkable destination must never start")
    var adjusted = policy("adjusted")
    check(adjusted.choose(Vector3.ZERO,"fixture",now,true,func(p:Vector3)->Dictionary:return {"allowed":true,"position":p+Vector3(8,0,0)}).is_empty(),"Destination adjustment outside small recalled region must be rejected")
    source(now,[100,0])
    var far = policy("far")
    check(far.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed")).is_empty(),"Distant regions outside resident obstacle radius must not cause long detours")
    source(now)
    var visible = policy("visible")
    check(visible.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"),{"world_id":"fixture","source":"local_physics_eye_sensor","logical_time_ms":now,"visible_entities":[{"entity_id":"fixture:rabbit:0"}]}).is_empty(),"Already visible animal needs no retrospective search")
    var stale = policy("stale")
    source(now-16000)
    check(stale.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed")).is_empty(),"Logically stale forecast cannot create intent")
    source(now)
    var ordinary_public = load("res://nov_animal_search_panel.gd").new()
    root.add_child(ordinary_public);ordinary_public.set_process(false);ordinary_public.enabled=true;ordinary_public.set_world("fixture")
    var status = JSON.parse_string(FileAccess.get_file_as_string(directory+"/policy.public"))
    check(ordinary_public._accept(JSON.stringify(status),"intent"),"Browser may consume native presentation intent")
    check(not ordinary_public.intent(-1,now).is_empty(),"Fresh native intent reaches browser presentation")
    check(ordinary_public.intent(Time.get_unix_time_from_system()+16,now).is_empty(),"Native intent expires promptly during outage")
    check(ordinary_public.intent(-1,now+60000).is_empty(),"Browser cannot extend native logical deadline")
    status.intent.goal=[100001,0,0]
    check(not ordinary_public._accept(JSON.stringify(status),"intent"),"Invalid public goal cannot steer browser")
    var sensor = load("res://nov_visual_perception.gd").new()
    var host := Node3D.new();root.add_child(host)
    var body := CharacterBody3D.new();host.add_child(body);body.position=Vector3(0,.9,0)
    var rabbit := StaticBody3D.new();rabbit.collision_layer=1;host.add_child(rabbit);rabbit.position=Vector3(8,0,0)
    var rabbit_shape := CollisionShape3D.new();rabbit_shape.shape=BoxShape3D.new();rabbit_shape.shape.size=Vector3(1,1,1);rabbit.add_child(rabbit_shape);rabbit_shape.position.y=.5
    var wall := StaticBody3D.new();wall.collision_layer=1;host.add_child(wall);wall.position=Vector3(4,1,0)
    var wall_shape := CollisionShape3D.new();wall_shape.shape=BoxShape3D.new();wall_shape.shape.size=Vector3(1,3,4);wall.add_child(wall_shape)
    sensor.register_target(rabbit,"fixture:rabbit:0","rabbit","fixture",Vector3(0,.5,0))
    sensor.observation_ready.connect(Callable(value,"observe"))
    await physics_frame
    sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",now+100,1.0)
    check(value._counts.memory.confirmed==0 and not value._active.is_empty(),"Occluded physical animal cannot confirm search")
    wall.queue_free()
    await physics_frame
    await physics_frame
    sensor.scan(body,Vector3.RIGHT,host.get_world_3d().direct_space_state,"fixture",now+200,1.0)
    check(value._counts.memory.confirmed==1 and value._active.is_empty(),"Only new ray-confirmed sighting closes successful search")
    check(value._last_ms==now+200,"Confirmation timestamp must be persisted before restart")
    var reopened = policy()
    check(not reopened._failed,"Valid confirmed checkpoint must survive reopen")
    check(reopened.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed")).is_empty() and not reopened._failed,"Startup waits for interpolated logical clock to catch persisted checkpoint")
    source(now+1000)
    check(reopened.choose(Vector3.ZERO,"fixture",now+1000,true,Callable(self,"allowed")).is_empty(),"Restart cannot bypass five-minute cooldown")
    var second := now+300201
    source(second);reopened._next_poll=0
    var baseline: Dictionary = reopened.choose(Vector3.ZERO,"fixture",second,true,Callable(self,"allowed"))
    check(baseline.get("arm")=="last_seen" and baseline.goal==[12.0,0.0,0.0],"Next search must alternate to last-seen baseline")
    reopened.choose(Vector3(12,0,0),"fixture",second+100,true,Callable(self,"allowed"))
    check(reopened._active.phase=="scan","Arrival switches to bounded look-around without teleportation")
    reopened.choose(Vector3(12,0,0),"fixture",second+4100,true,Callable(self,"allowed"))
    check(absf(float(reopened._active.heading)-PI)<0.01,"Physical body scans while camera can remain stable")
    reopened.save(true)
    status=JSON.parse_string(FileAccess.get_file_as_string(directory+"/policy.public"))
    check(ordinary_public._accept(JSON.stringify(status),"intent"),"Scanning native intention must reach presentation")
    check(absf(float(ordinary_public.intent(-1,second+5100).get("heading",0))-TAU*5.0/8.0)<0.01,"Browser interpolates heading from authoritative clock instead of jumping on each heartbeat")
    reopened.choose(Vector3(12,0,0),"fixture",second+8100,true,Callable(self,"allowed"))
    check(reopened._active.is_empty() and reopened._counts.last_seen.not_observed==1,"Search without contact ends after scan budget")
    check(reopened._results.back().absence_claim==false,"Budget exhaustion cannot claim animal absence")
    var stalled = policy("stalled")
    source(now);stalled.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"))
    stalled.choose(Vector3.ZERO,"fixture",now+15001,true,Callable(self,"allowed"))
    check(stalled._active.is_empty() and stalled._results.back().result=="no_progress","Unchanged approach abandons search before stuck recovery")
    var resumed = policy("resume")
    source(now);resumed.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"))
    var after_restart = policy("resume")
    after_restart.choose(Vector3.ZERO,"fixture",now+500,true,Callable(self,"allowed"))
    check(after_restart._active.is_empty() and after_restart._counts.memory.aborted==1,"Restart closes interrupted intent without replay")
    var quota = policy("quota")
    for i in range(4):
        var stamp := now+i*300001
        source(stamp);quota._next_poll=0
        quota.choose(Vector3.ZERO,"fixture",stamp,true,Callable(self,"allowed"))
        quota.finish("not_observed_within_budget")
    source(now+4*300001);quota._next_poll=0
    check(quota.choose(Vector3.ZERO,"fixture",now+4*300001,true,Callable(self,"allowed")).is_empty(),"At most four searches per logical day/night cycle")
    source(3600001);quota._next_poll=0
    check(not quota.choose(Vector3.ZERO,"fixture",3600001,true,Callable(self,"allowed")).is_empty(),"New cycle restores quota after cooldown")
    var paused = policy("paused")
    source(now);paused.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"))
    paused.suspend("clock_unavailable")
    check(paused.choose(Vector3.ZERO,"fixture",now-100,true,Callable(self,"allowed")).is_empty() and not paused._failed,"Pause/resume waits for clock interpolation without replay or permanent failure")
    paused.choose(Vector3.ZERO,"fixture",now+500,true,Callable(self,"allowed"))
    check(paused._active.is_empty() and paused._serial==1,"Pause cannot bypass cooldown or duplicate search")
    var mismatch = policy("mismatch")
    source(now);mismatch.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"))
    check(mismatch.choose(Vector3.ZERO,"other",now+500,true,Callable(self,"allowed")).is_empty() and mismatch._failed,"World swap must fail closed")
    var rewind = policy("rewind")
    source(now);rewind.choose(Vector3.ZERO,"fixture",now,true,Callable(self,"allowed"))
    check(rewind.choose(Vector3.ZERO,"fixture",now-1,true,Callable(self,"allowed")).is_empty() and rewind._failed,"Logical clock rewind must fail closed")
    var corrupt := FileAccess.open(directory+"/bad",FileAccess.WRITE);corrupt.store_string("{}");corrupt.close()
    check(policy("bad")._failed,"Corrupt checkpoint cannot reset budgets or fabricate history")
    check(FileAccess.get_unix_permissions(directory+"/policy")==384,"Policy checkpoint must be private")
    check(FileAccess.get_unix_permissions(directory+"/policy.public")==420,"Presentation projection must be public read-only")
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    await physics_frame
    stage.get_node("LiveFeed").enabled=false
    stage._local_motion._episodes.context={"world_id":"fixture"}
    stage._day_cycle.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"fixture","paused":false,"tick":200,"tick_duration_ms":500,"logical_time_ms":100000,"cycle_ms":3600000})
    var before: Vector3 = stage._position
    var accepted := false
    for direction in range(8):
        var offset := Vector2.RIGHT.rotated(TAU*float(direction)/8.0)*8.0
        var ground: Vector3 = stage._local_motion._traversability.ground_position(before.x+offset.x,before.z+offset.y)
        var resolution: Dictionary = stage._local_motion.resolve_destination(ground)
        if bool(resolution.get("allowed",false)) and resolution.position.distance_to(ground)<=4.0:
            source(now,[resolution.position.x,resolution.position.z]);accepted=true;break
    check(accepted,"Real scene must provide a locally clear test search endpoint")
    stage._animal_search_intent.configure(directory+"/integration",directory+"/integration.public",directory+"/forecast",session)
    stage._route_goal.reset();stage._last_live_position=before
    stage._advance_live_walk(0.05)
    check(not stage._animal_search_selection.is_empty(),"Real renderer must select a bounded search through actual destination resolver")
    check(stage._position.distance_to(before)<=0.8,"Search must use incremental physical movement rather than teleportation")
    check(not stage._animal_search_route.is_empty(),"Search intention must bind a distinct physical journey")
    stage._animal_search_intent.finish("integration_test_complete")
    stage.queue_free()
    host.queue_free();ordinary_public.queue_free()
    await process_frame
    for filename in DirAccess.get_files_at(directory):DirAccess.remove_absolute(directory+"/"+filename)
    DirAccess.remove_absolute(directory)
    print("Bounded animal search smoke: ",failures," failures")
    quit(1 if failures else 0)
