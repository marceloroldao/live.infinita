extends Node3D
const Rabbit = preload("res://nov_rabbit.gd")
const SCHEMA := "live-infinita-physical-wildlife/v1"
const COUNT := 3
var _authority := false
var _checkpoint := ""
var _projection := ""
var _world := ""
var _animals: Array = []
var _home := Vector3.ZERO
var _water := Vector3.ZERO
var _food := Vector3.ZERO
var _loaded: Dictionary = {}
var _last_time := -1
var _last_publish_ms := -10000
var _failed := false
var _sequence := 0
var _resources: Node3D
var _http: HTTPRequest
var _poll_elapsed := 0.0
var _busy := false
var _replica_received_ms := -10000
var _last_replica_sequence := -1
var _last_replica_time := -1

func configure(authority: bool, checkpoint: String = "", projection: String = "") -> void:
    _authority = authority
    _checkpoint = checkpoint;_projection = projection
    if authority and not checkpoint.is_empty() and FileAccess.file_exists(checkpoint):
        if FileAccess.get_file_as_bytes(checkpoint).size()>32768:
            _failed = true;return
        var envelope = _json(FileAccess.get_file_as_string(checkpoint))
        if typeof(envelope)!=TYPE_DICTIONARY or typeof(envelope.get("payload"))!=TYPE_STRING or envelope.get("sha256")!=str(envelope.get("payload","")).sha256_text():
            _failed = true;push_warning("WILDLIFE_CHECKPOINT_INVALID");return
        var value = _json(envelope["payload"])
        if not valid_snapshot(value):
            _failed = true;push_warning("WILDLIFE_CHECKPOINT_INVALID");return
        _loaded = value
    if not authority and OS.has_feature("web"):
        _http = HTTPRequest.new();_http.timeout = 3.0;_http.body_size_limit = 32768
        add_child(_http);_http.request_completed.connect(_received)

func _json(raw: String) -> Variant:
    var parser := JSON.new()
    return parser.data if parser.parse(raw)==OK else null

func vector(value: Array) -> Vector3:
    return Vector3(float(value[0]),float(value[1]),float(value[2]))

func finite_vector(value: Variant, count: int) -> bool:
    if typeof(value)!=TYPE_ARRAY or value.size()!=count:return false
    for number in value:
        if typeof(number) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(number)) or absf(float(number))>100000:return false
    return true

func valid_snapshot(value: Variant) -> bool:
    if typeof(value)!=TYPE_DICTIONARY or value.get("schema")!=SCHEMA or value.get("authority")!="native_renderer_physics" or value.get("species")!="rabbit" or typeof(value.get("world_id"))!=TYPE_STRING or str(value["world_id"]).is_empty() or str(value["world_id"]).length()>160:return false
    for key in ["logical_time_ms","sequence","generated_at_unix"]:
        var n = value.get(key)
        if typeof(n) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(n)) or float(n)<0:return false
    for key in ["home","water","food"]:
        if not finite_vector(value.get(key),3):return false
    var rows = value.get("animals")
    if typeof(rows)!=TYPE_ARRAY or rows.size()!=COUNT:return false
    var seen: Dictionary = {}
    var home := vector(value["home"])
    for resource in ["water","food"]:
        if vector(value[resource]).distance_to(home)>12.0:return false
    for row in rows:
        if typeof(row)!=TYPE_DICTIONARY or typeof(row.get("id"))!=TYPE_STRING or not str(row["id"]).begins_with(str(value["world_id"])+":rabbit:") or seen.has(row["id"]):return false
        seen[row["id"]] = true
        if not finite_vector(row.get("position"),3) or not finite_vector(row.get("heading"),2):return false
        if absf(Vector2(row["heading"][0],row["heading"][1]).length()-1.0)>0.01:return false
        var pos := vector(row["position"])
        if Vector2(pos.x-home.x,pos.z-home.z).length()>21.0 or absf(pos.y-home.y)>20.0:return false
        for key in ["hunger","thirst","phase","consumed_food","consumed_water","blocked_steps"]:
            var n = row.get(key)
            if typeof(n) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(n)) or float(n)<0:return false
        if float(row["hunger"])>1 or float(row["thirst"])>1 or str(row.get("mode")) not in ["wander","rest","flee","seek_water","drink","seek_food","graze"]:return false
    return true

func _create(value: Dictionary, sensor: RefCounted) -> bool:
    _world = value["world_id"]
    _home = vector(value["home"]);_water = vector(value["water"]);_food = vector(value["food"])
    _sequence = int(value["sequence"])
    for i in range(COUNT):
        var rabbit = Rabbit.new()
        rabbit.build(value["animals"][i]["id"],i)
        add_child(rabbit);rabbit.restore(value["animals"][i])
        if not sensor.register_target(rabbit,rabbit.identity,"rabbit",_world,Vector3(0,0.12,0)):
            rabbit.queue_free();_failed = true;return false
        _animals.append(rabbit)
    _build_resources()
    print("WILDLIFE_ACTIVE world=%s count=3 authority=%s" % [_world,str(_authority)])
    return true

func _build_resources() -> void:
    _resources = Node3D.new();add_child(_resources)
    for entry in [[_water,1.2,Color("#398faf")],[_food,2.0,Color("#75904a")]]:
        var visual := MeshInstance3D.new()
        var mesh := CylinderMesh.new()
        mesh.top_radius = entry[1];mesh.bottom_radius = entry[1];mesh.height = 0.035;mesh.radial_segments = 16
        visual.mesh = mesh;visual.position = entry[0]+Vector3.UP*0.025
        var material := StandardMaterial3D.new();material.albedo_color = entry[2];material.roughness = 0.8
        visual.material_override = material;_resources.add_child(visual)
    # Explicit resource patches for a first habitat; not a simulated hydrology system.

func _floor(location: Vector3, space: PhysicsDirectSpaceState3D) -> Dictionary:
    var ray := PhysicsRayQueryParameters3D.create(location+Vector3.UP*2.0,location-Vector3.UP*3.0,1)
    var hit := space.intersect_ray(ray)
    if hit.is_empty() or hit["normal"].y<0.90 or absf(hit["position"].y-location.y)>2.0:return {}
    return hit

func _spawn(observer: CharacterBody3D, space: PhysicsDirectSpaceState3D, world: String, time_ms: int, sensor: RefCounted) -> bool:
    var feet := observer.global_position-Vector3.UP*0.9
    for angle in [0.0,0.8,-0.8,1.6,-1.6,PI]:
        var direction := Vector3.BACK.rotated(Vector3.UP,angle)
        var floor_hit := _floor(feet+direction*15.0,space)
        if floor_hit.is_empty():continue
        var home: Vector3 = floor_hit["position"]
        var water_hit := _floor(home+Vector3(5,0,0),space)
        var food_hit := _floor(home+Vector3(-5,0,0),space)
        if water_hit.is_empty() or food_hit.is_empty():continue
        var rows: Array = []
        for i in range(COUNT):
            var point := _floor(home+Vector3(float(i-1)*2.0,0,2),space)
            if point.is_empty():break
            var pos: Vector3 = point["position"]+Vector3.UP*Rabbit.CENTER_Y
            var shape := CapsuleShape3D.new();shape.radius = Rabbit.RADIUS;shape.height = Rabbit.CENTER_Y*2.0-0.04
            var query := PhysicsShapeQueryParameters3D.new();query.shape = shape;query.transform = Transform3D(Basis.IDENTITY,pos);query.collision_mask = 1
            if not space.intersect_shape(query,1).is_empty():break
            rows.append({"id":world+":rabbit:"+str(i),"position":[pos.x,pos.y,pos.z],"heading":[0,1],"hunger":0.42+float(i)*0.12,"thirst":0.48+float(i)*0.10,"mode":"wander","phase":float(i)*7.0,"consumed_food":0,"consumed_water":0,"blocked_steps":0})
        if rows.size()!=COUNT:continue
        var value := {"schema":SCHEMA,"authority":"native_renderer_physics","species":"rabbit","world_id":world,"logical_time_ms":time_ms,"sequence":0,"generated_at_unix":Time.get_unix_time_from_system(),"home":[home.x,home.y,home.z],"water":[water_hit["position"].x,water_hit["position"].y,water_hit["position"].z],"food":[food_hit["position"].x,food_hit["position"].y,food_hit["position"].z],"animals":rows}
        return _create(value,sensor)
    return false

func snapshot(time_ms: int) -> Dictionary:
    var rows: Array = []
    for rabbit in _animals:rows.append(rabbit.snapshot())
    return {"schema":SCHEMA,"authority":"native_renderer_physics","species":"rabbit","world_id":_world,
        "logical_time_ms":time_ms,"sequence":_sequence,"generated_at_unix":Time.get_unix_time_from_system(),
        "home":[_home.x,_home.y,_home.z],"water":[_water.x,_water.y,_water.z],"food":[_food.x,_food.y,_food.z],
        "animals":rows,"learning":false,"memory_writes":false}

func _atomic(path: String, encoded: String, permissions: int) -> bool:
    if path.is_empty():return true
    var file := FileAccess.open(path+".tmp",FileAccess.WRITE)
    if file==null:return false
    file.store_string(encoded);file.flush();file.close()
    if FileAccess.set_unix_permissions(path+".tmp",permissions)!=OK:return false
    return DirAccess.rename_absolute(path+".tmp",path)==OK

func persist(time_ms: int) -> bool:
    _sequence += 1
    var payload := JSON.stringify(snapshot(time_ms))
    _last_publish_ms = Time.get_ticks_msec()
    if not _atomic(_checkpoint,JSON.stringify({"payload":payload,"sha256":payload.sha256_text()}),384):return false
    return _atomic(_projection,payload,420)

func update(clock: RefCounted, observer: CharacterBody3D, sensor: RefCounted, space: PhysicsDirectSpaceState3D, world: String, live: bool) -> void:
    if _failed or not live or not clock._synced or world.is_empty() or world!=clock._world_id:return
    var time_ms := floori(clock._logical_ms+clock._elapsed*1000.0)
    if not _authority:
        _poll_elapsed += 1.0/60.0
        if _http!=null and not _busy and _poll_elapsed>=0.5:
            _poll_elapsed = 0.0
            var url := str(JavaScriptBridge.eval("window.location.origin"))+"/godot/wildlife/state.json?t="+str(Time.get_ticks_msec())
            _busy = _http.request(url)==OK
        if not _loaded.is_empty() and str(_loaded["world_id"])==world:
            if _animals.is_empty():_create(_loaded,sensor)
            elif _world==world:
                for i in range(COUNT):_animals[i].restore(_loaded["animals"][i])
            _loaded = {}
        visible = Time.get_ticks_msec()-_replica_received_ms<=10000 and _world==world
        for rabbit in _animals:rabbit.collision_layer = 1 if visible else 0
        return
    if not _world.is_empty() and _world!=world:
        _failed = true;push_warning("WILDLIFE_WORLD_MISMATCH");return
    if _animals.is_empty():
        if not _loaded.is_empty():
            if _loaded["world_id"]!=world:_failed = true;return
            if not _create(_loaded,sensor):return
            _loaded = {}
        elif not _spawn(observer,space,world,time_ms,sensor):return
        _last_time = time_ms
        if not persist(time_ms):_failed = true;push_warning("WILDLIFE_SAVE_FAILED")
        return
    if time_ms<_last_time:return
    var dt := minf(0.1,float(time_ms-_last_time)/1000.0)
    _last_time = time_ms
    # No unloaded-terrain simulation, pursuit teleport or offline catch-up.
    var active := observer.global_position.distance_to(_home)<42.0
    for rabbit in _animals:
        if active and not rabbit.support(rabbit.global_position,space,[rabbit.get_rid()]).is_empty():
            rabbit.step(dt,_water,_food,_home,observer,space)
    if Time.get_ticks_msec()-_last_publish_ms>=500:
        if not persist(time_ms):_failed = true;push_warning("WILDLIFE_SAVE_FAILED")

func _received(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    _busy = false
    if result!=HTTPRequest.RESULT_SUCCESS or code!=200:return
    accept_replica(JSON.parse_string(body.get_string_from_utf8()))

func accept_replica(value: Variant) -> bool:
    if _authority or not valid_snapshot(value):return false
    var age := Time.get_unix_time_from_system()-float(value["generated_at_unix"])
    if age>10.0 or age < -3.0:return false
    if not _world.is_empty() and value["world_id"]!=_world:return false
    if int(value["sequence"])<_last_replica_sequence or int(value["logical_time_ms"])<_last_replica_time:return false
    _last_replica_sequence = int(value["sequence"])
    _last_replica_time = int(value["logical_time_ms"])
    _loaded = value.duplicate(true);_replica_received_ms = Time.get_ticks_msec()
    return true
