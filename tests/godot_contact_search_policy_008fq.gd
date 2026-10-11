extends SceneTree
var checks:=0
var failures:=0
var directory:=""
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:push_error(label);failures+=1
func allowed(point:Vector3)->Dictionary:return {"allowed":true,"position":point}
func sight(stamp:int)->Dictionary:
    return {"schema":"live-infinita-nov-visual-observation/v1","source":"local_physics_eye_sensor","observer_entity_id":"nov","world_write_authority":false,"absence_claim":false,"logical_time_ms":stamp,"world_id":"w",
        "visible_entities":[{"entity_id":"w:rabbit:1","kind":"rabbit","evidence":"eye_ray_unobstructed","observed_position_m":[10,0,0]}]}
func seeded(name:String,flag:String="1"):
    OS.set_environment("LIVE_INFINITA_ANIMAL_CONTACT_SEARCH_ENABLED",flag)
    var p=load("res://nov_animal_search_intent.gd").new()
    p.configure(directory+"/"+name,directory+"/"+name+".public",directory+"/source","a".repeat(32))
    p.choose(Vector3.ZERO,"w",100000,false,Callable(self,"allowed"))
    p.observe(sight(100000))
    check(p.choose(Vector3.ZERO,"w",100000,false,Callable(self,"allowed")).get("arm")=="visible","approach starts")
    return p
func published(p)->Dictionary:return JSON.parse_string(FileAccess.get_file_as_string(p._public))
func _initialize()->void:call_deferred("run")
func run()->void:
    directory="/tmp/contact-policy-"+Crypto.new().generate_random_bytes(8).hex_encode()
    DirAccess.make_dir_recursive_absolute(directory)
    OS.set_environment("LIVE_INFINITA_ANIMAL_APPROACH_ENABLED","1")
    var off=seeded("off","0")
    check(off.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed")).is_empty(),"flag off retains lost-contact stop")
    check(off._contact_search.journal.records.is_empty(),"disabled search reserves no durable attempt")
    var p=seeded("on")
    var selection:Dictionary=p.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed"))
    check(selection.get("arm")=="contact_search" and selection.id==p._approach._results[0].id+":contact-search","new route identity on real contact loss")
    check(p._contact_search.journal.pending.result=="reserved" and published(p).active,"durable reserve precedes public movement")
    p.suspend("clock_unavailable")
    check(p._contact_search.result.result=="invalid_context" and not published(p).active,"feed or clock suspension immediately clears public recovery")
    check(p._contact_search.journal.pending.is_empty(),"suspension settles reservation")
    var cold=load("res://nov_animal_search_intent.gd").new()
    cold.configure(p._path,directory+"/cold.public",directory+"/source","a".repeat(32))
    check(cold._contact_search.journal.ready and cold._contact_search.journal.records.size()==1,"cancelled attempt survives cold native policy")
    var world=seeded("world")
    world.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed"))
    check(world.choose(Vector3.ZERO,"different",102100,false,Callable(self,"allowed")).is_empty() and world._contact_search.result.result=="invalid_context" and not published(world).active,"world change cancels recovery")
    var rewind=seeded("rewind")
    rewind.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed"))
    check(rewind.choose(Vector3.ZERO,"w",101999,false,Callable(self,"allowed")).is_empty() and rewind._contact_search.result.result=="invalid_context","clock rewind cancels recovery")
    var exhausted=seeded("exhausted")
    exhausted.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed"))
    check(exhausted.choose(Vector3.ZERO,"w",107000,false,Callable(self,"allowed")).is_empty() and exhausted._contact_search.result.result=="search_budget_exhausted" and not published(exhausted).active,"logical budget clears public intent")
    var interrupted=seeded("interrupted")
    interrupted.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed"))
    cold=load("res://nov_animal_search_intent.gd").new()
    cold.configure(interrupted._path,directory+"/restart.public",directory+"/source","a".repeat(32))
    check(cold._contact_search.journal.ready and cold._contact_search.journal.records[0].result=="renderer_restart" and cold._contact_search.journal.records[0].distance_m==null,"pending cold restart archives unknown distance without resuming")
    var historical=seeded("historical")
    historical._approach.choose(Vector3.ZERO,"w",102000,Callable(self,"allowed"))
    check(historical.choose(Vector3.ZERO,"w",102000,false,Callable(self,"allowed")).is_empty() and historical._contact_search.journal.pending.is_empty(),"old completed approach cannot start recovery")
    var stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    await physics_frame
    stage.get_node("LiveFeed").enabled=false
    stage._local_motion._episodes.context={"world_id":"w"}
    stage._day_cycle.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"w","paused":false,"tick":200,"tick_duration_ms":500,"logical_time_ms":100000,"cycle_ms":3600000})
    stage._animal_search_intent.configure(directory+"/scene",directory+"/scene.public",directory+"/source","a".repeat(32))
    var before:Vector3=stage._position
    stage._animal_search_intent.choose(before,"w",100000,false,Callable(stage._local_motion,"resolve_destination"))
    var walkable:=false
    for i in range(8):
        var direction:=Vector2.RIGHT.rotated(TAU*i/8.0)
        var point:=before+Vector3(direction.x,0,direction.y)*10.0
        var goal:=point-Vector3(direction.x,0,direction.y)*5.0
        if not stage._local_motion.resolve_destination(goal).get("allowed",false):continue
        # Adapter fixture from current coordinates; separate from the real-eye physical smoke.
        var row:=sight(100000);row.visible_entities[0].observed_position_m=[point.x,point.y,point.z]
        stage._animal_search_intent.observe(row);walkable=true;break
    check(walkable,"native scene has walkable last-observed destination")
    stage._advance_live_walk(.05)
    check(stage._animal_search_selection.get("arm")=="visible","native live walk starts physical approach route")
    stage._day_cycle.apply_clock({"schema":"live-infinita-sky-clock/v1","source":"persisted_simulation_clock","world_id":"w","paused":false,"tick":204,"tick_duration_ms":500,"logical_time_ms":102000,"cycle_ms":3600000})
    before=stage._position
    stage._advance_live_walk(.05)
    check(stage._animal_search_selection.get("arm")=="contact_search","native live walk switches route to last-sighting recovery")
    check(stage._position.distance_to(before)>0 and stage._position.distance_to(before)<.8,"contact search uses incremental existing native locomotion")
    stage._animal_search_intent.finish("navigation_recovery")
    check(not published(stage._animal_search_intent).active and stage._animal_search_intent._contact_search.result.result=="invalid_context","navigation recovery cancels and publishes stopped search")
    stage.queue_free();await process_frame
    for file in DirAccess.get_files_at(directory):DirAccess.remove_absolute(directory+"/"+file)
    DirAccess.remove_absolute(directory)
    print("008FQ_POLICY checks="+str(checks)+" failures="+str(failures))
    quit(1 if failures else 0)
