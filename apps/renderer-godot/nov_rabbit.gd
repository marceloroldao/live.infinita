extends CharacterBody3D
# Programmed physiology; no learned animal intelligence in this stage.
var identity := ""
var hunger := 0.35
var thirst := 0.35
var mode := "wander"
var phase := 0.0
var heading := Vector3.BACK
var consumed_food := 0
var consumed_water := 0
var blocked_steps := 0
var _legs: Array[Node3D] = []
var _head: Node3D
const RADIUS := 0.28
const CENTER_Y := 0.38

func build(id: String, index: int) -> void:
    identity = id
    name = "Rabbit_"+str(index)
    collision_layer = 1
    collision_mask = 1
    var collision := CollisionShape3D.new()
    var shape := CapsuleShape3D.new()
    shape.radius = RADIUS
    shape.height = CENTER_Y*2.0
    collision.shape = shape
    add_child(collision)
    var fur := Color("#b6a08a").lerp(Color("#d7c7aa"),float(index)/3.0)
    _ellipsoid(self,Vector3(0,0,0),Vector3(0.30,0.27,0.47),fur)
    _head = Node3D.new()
    _head.position = Vector3(0,0.14,0.34)
    add_child(_head)
    _ellipsoid(_head,Vector3.ZERO,Vector3(0.23,0.23,0.24),fur)
    for side in [-1.0,1.0]:
        _ellipsoid(_head,Vector3(side*0.10,0.34,-0.03),Vector3(0.065,0.30,0.075),fur)
        _ellipsoid(_head,Vector3(side*0.10,0.34,0.035),Vector3(0.032,0.22,0.012),Color("#b9817c"))
        _ellipsoid(_head,Vector3(side*0.17,0.04,0.16),Vector3(0.025,0.035,0.025),Color("#222323"))
        for z in [-0.25,0.24]:
            var leg := Node3D.new()
            leg.position = Vector3(side*0.20,-0.20,z)
            add_child(leg)
            _ellipsoid(leg,Vector3(0,-0.05,0.03),Vector3(0.09,0.12,0.15),fur)
            _legs.append(leg)
    _ellipsoid(self,Vector3(0,0.02,-0.45),Vector3(0.13,0.13,0.13),Color("#e5ddd0"))

func _ellipsoid(parent: Node3D, location: Vector3, size: Vector3, color: Color) -> void:
    var visual := MeshInstance3D.new()
    var mesh := SphereMesh.new()
    mesh.radius = 1.0;mesh.height = 2.0;mesh.radial_segments = 8;mesh.rings = 4
    visual.mesh = mesh;visual.scale = size;visual.position = location
    var material := StandardMaterial3D.new()
    material.albedo_color = color;material.roughness = 1.0
    visual.material_override = material
    parent.add_child(visual)

func snapshot() -> Dictionary:
    return {"id":identity,"position":[global_position.x,global_position.y,global_position.z],
        "heading":[heading.x,heading.z],"hunger":hunger,"thirst":thirst,"mode":mode,
        "phase":phase,"consumed_food":consumed_food,"consumed_water":consumed_water,"blocked_steps":blocked_steps}

func restore(row: Dictionary) -> void:
    var p: Array = row["position"]
    global_position = Vector3(p[0],p[1],p[2])
    heading = Vector3(row["heading"][0],0,row["heading"][1])
    hunger = row["hunger"];thirst = row["thirst"];mode = row["mode"];phase = row["phase"]
    consumed_food = row["consumed_food"];consumed_water = row["consumed_water"];blocked_steps = row["blocked_steps"]
    animate(0.0)

func sees_threat(observer: CharacterBody3D, space: PhysicsDirectSpaceState3D) -> bool:
    if not is_instance_valid(observer):return false
    var aim := observer.global_position
    if aim.distance_to(global_position)>9.0:return false
    var ray := PhysicsRayQueryParameters3D.create(global_position+Vector3.UP*0.18,aim,1,[get_rid()])
    var hit := space.intersect_ray(ray)
    return hit.is_empty() or hit.get("collider")==observer

func step(dt: float, water: Vector3, food: Vector3, home: Vector3, observer: CharacterBody3D, space: PhysicsDirectSpaceState3D) -> void:
    if dt<=0.0 or not is_finite(dt):return
    dt = minf(dt,0.1)
    hunger = minf(1.0,hunger+dt/160.0)
    thirst = minf(1.0,thirst+dt/120.0)
    phase += dt
    var target := home+Vector3(sin(phase*0.08+float(identity.hash()%11))*7.0,0,cos(phase*0.11)*7.0)
    var speed := 1.3
    if sees_threat(observer,space):
        mode = "flee"
        target = global_position+(global_position-observer.global_position).normalized()*8.0
        speed = 3.1
    elif thirst>=0.62 or (mode=="drink" and thirst>0.2):
        mode = "seek_water";target = water
        if Vector2(global_position.x-water.x,global_position.z-water.z).length()<1.5:
            mode = "drink";thirst = maxf(0.0,thirst-dt*0.3)
            if thirst<=0.2 and thirst+dt*0.3>0.2:consumed_water += 1
            animate(0.0);return
    elif hunger>=0.60 or (mode=="graze" and hunger>0.2):
        mode = "seek_food";target = food
        if Vector2(global_position.x-food.x,global_position.z-food.z).length()<2.0:
            mode = "graze";hunger = maxf(0.0,hunger-dt*0.25)
            if hunger<=0.2 and hunger+dt*0.25>0.2:consumed_food += 1
            animate(0.0);return
    elif fposmod(phase,36.0)>28.0:
        mode = "rest";animate(0.0);return
    else:mode = "wander"
    if Vector2(global_position.x-home.x,global_position.z-home.z).length()>18.0:
        target = home
    var wanted := Vector3(target.x-global_position.x,0,target.z-global_position.z).normalized()
    var moved := false
    for angle in [0.0,0.55,-0.55,1.1,-1.1,1.8,-1.8,PI]:
        var direction := wanted.rotated(Vector3.UP,angle)
        var next := global_position+direction*speed*dt
        if Vector2(next.x-home.x,next.z-home.z).length()>20.0:continue
        var ground := support(next,space,[get_rid()])
        if ground.is_empty():continue
        var y := float(ground["position"].y)+CENTER_Y
        if absf(y-global_position.y)>0.30:continue
        var motion := Vector3(next.x,y,next.z)-global_position
        if test_move(global_transform,motion):continue
        var old := global_position
        move_and_collide(motion)
        moved = global_position.distance_to(old)>0.0001
        if moved:heading = direction
        break
    if not moved:blocked_steps += 1
    animate(speed if moved else 0.0)

func support(location: Vector3, space: PhysicsDirectSpaceState3D, exclude: Array = []) -> Dictionary:
    var excluded: Array[RID] = []
    excluded.assign(exclude)
    var ray := PhysicsRayQueryParameters3D.create(location+Vector3.UP*1.0,location-Vector3.UP*1.3,1,excluded)
    var hit := space.intersect_ray(ray)
    if hit.is_empty() or hit["normal"].y<0.82:return {}
    return hit

func animate(speed: float) -> void:
    rotation.y = atan2(heading.x,heading.z)
    for i in range(_legs.size()):_legs[i].rotation.x = sin(phase*10.0+float(i%2)*PI)*0.40*minf(1.0,speed)
    if _head != null:_head.rotation.x = 0.45 if mode in ["drink","graze"] else 0.0
