extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures += 1
func _initialize() -> void:call_deferred("run")
func run() -> void:
    var holder := Node3D.new();root.add_child(holder)
    var observer := CharacterBody3D.new();observer.position = Vector3(0,0.9,0);holder.add_child(observer)
    var target := Node3D.new();target.position = Vector3(0,0.4,8);holder.add_child(target)
    var hidden := Node3D.new();hidden.position = Vector3(0,0.4,40);holder.add_child(hidden)
    var sensor = load("res://nov_visual_perception.gd").new()
    sensor.register_target(target,"test:rabbit:0","rabbit","test",Vector3(0,0.15,0))
    sensor.register_target(hidden,"test:rabbit:1","rabbit","test",Vector3.ZERO)
    var path := "/tmp/animal-encounters-"+str(OS.get_process_id())
    var recorder = load("res://nov_animal_encounters.gd").new();recorder.configure(path,path+".ack")
    sensor.observation_ready.connect(Callable(recorder,"observe"))
    await physics_frame
    var space := holder.get_world_3d().direct_space_state
    sensor.scan(observer,Vector3.BACK,space,"test",1000,1.0)
    sensor.scan(observer,Vector3.BACK,space,"test",1000,1.0)
    sensor.scan(observer,Vector3.BACK,space,"test",1250,1.0)
    check(recorder._active.size()==1 and recorder._active["test:rabbit:0"]["sample_count"]==2,"Only real in-range eye sightings count; paused/replayed frame does not")
    var wall := StaticBody3D.new();wall.position = Vector3(0,1.5,4)
    var collision := CollisionShape3D.new();var shape := BoxShape3D.new();shape.size = Vector3(4,3,0.5);collision.shape = shape;wall.add_child(collision);holder.add_child(wall)
    await physics_frame;await physics_frame
    sensor.scan(observer,Vector3.BACK,space,"test",2000,1.0)
    check(recorder._pending.is_empty(),"Brief lost sight does not instantly finish encounter")
    sensor.scan(observer,Vector3.BACK,space,"test",4500,1.0)
    check(recorder._pending.size()==1 and recorder._pending[0]["sample_count"]==2,"Occluded animal adds no samples and seals observed encounter")
    check(recorder._pending[0]["last_seen_ms"]==1250 and recorder._pending[0]["closed_reason"]=="lost_visual_contact","No unseen position or fabricated end sighting")
    check(not JSON.stringify(recorder.snapshot()).contains("test:rabbit:1"),"Global hidden animal identity never enters encounter journal")
    check(recorder.save(true),"Durable outbox saves physical encounter")
    var fixture_path := OS.get_environment("LIVE_INFINITA_ENCOUNTER_TEST_FIXTURE")
    if not fixture_path.is_empty():
        var fixture := FileAccess.open(fixture_path,FileAccess.WRITE)
        fixture.store_string(FileAccess.get_file_as_string(path));fixture.close()
    var loaded = load("res://nov_animal_encounters.gd").new();loaded.configure(path,path+".ack")
    check(loaded._pending==JSON.parse_string(JSON.stringify(recorder._pending)) and loaded._session==recorder._session,"Restart restores immutable pending record and stable session")
    var proof := JSON.stringify({"world_id":"test","session_id":recorder._session,"cursor":2})
    var ack := {"schema":recorder.ACK_SCHEMA,"world_id":"test","session_id":recorder._session,"cursor":2,"proof_payload":proof,"checksum":proof.sha256_text()}
    var file := FileAccess.open(path+".ack",FileAccess.WRITE);file.store_string(JSON.stringify(ack));file.close()
    sensor.scan(observer,Vector3.BACK,space,"test",4750,1.0)
    check(recorder._pending.size()==1,"Ack cannot advance beyond issued record")
    proof = JSON.stringify({"world_id":"test","session_id":recorder._session,"cursor":1})
    ack["cursor"]=1;ack["proof_payload"]=proof;ack["checksum"]=proof.sha256_text()
    file = FileAccess.open(path+".ack",FileAccess.WRITE);file.store_string(JSON.stringify(ack));file.close()
    sensor.scan(observer,Vector3.BACK,space,"test",5000,1.0)
    check(recorder._pending.is_empty() and recorder._acked==1,"Confirmed matching bridge cursor releases pending records")
    wall.queue_free();await physics_frame;await physics_frame
    for i in range(61):sensor.scan(observer,Vector3.BACK,space,"test",10000+i*500,1.0)
    check(recorder._pending.size()==1 and recorder._pending[0]["sequence"]==2 and recorder._pending[0]["sample_count"]==60,"Long contact coalesces bounded 30-second windows")
    var before := JSON.stringify(recorder.snapshot()["active"])
    sensor.scan(observer,Vector3.BACK,space,"other",41000,1.0)
    check(JSON.stringify(recorder.snapshot()["active"])==before,"Another world cannot merge encounters")
    var first: Dictionary = recorder._pending[0].duplicate(true)
    while recorder._pending.size()<128:
        var copy: Dictionary = first.duplicate(true);copy["sequence"] = recorder._next
        recorder._next += 1;recorder._pending.append(copy)
    sensor.scan(observer,Vector3.BACK,space,"test",70000,1.0)
    check(recorder._pending.size()==128 and recorder._pending[0]==first and recorder._dropped>0,"Backpressure preserves all unacknowledged encounters and counts ignored samples")
    var corrupt := FileAccess.open(path,FileAccess.WRITE);corrupt.store_string("bad");corrupt.close()
    var invalid = load("res://nov_animal_encounters.gd").new();invalid.configure(path,path+".ack")
    check(invalid._failed,"Damaged journal stops recording instead of forgetting pending encounters")
    for suffix in ["",".ack"]:DirAccess.remove_absolute(path+suffix)
    holder.queue_free();await process_frame
    print("008DT_ANIMAL_ENCOUNTERS_SMOKE failures=%d" % failures)
    quit(0 if failures==0 else 1)
