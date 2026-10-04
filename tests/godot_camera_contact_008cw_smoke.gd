extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func release_at(fps: int) -> float:
    var rig = load("res://nov_camera_stabilizer.gd").new()
    var dt := 1.0/float(fps)
    rig.constrain_arm(Vector3.ZERO,Vector3(0,0,7),3.0,dt,true)
    for i in range(fps*2):
        rig.constrain_arm(Vector3.ZERO,Vector3(0,0,7),7.0,dt)
    return rig._arm_length
func run() -> void:
    var rig = load("res://nov_camera_stabilizer.gd").new()
    var pivot := Vector3.ZERO
    var nominal := Vector3(0,0,7)
    rig.follow(nominal,Vector3.FORWARD,0.0,true)
    rig.constrain_arm(pivot,nominal,7.0,0.0,true)
    var contracted: Vector3 = rig.constrain_arm(pivot,nominal,3.0,1.0/60.0)
    check(contracted.length()<=3.001,"New obstruction must retract immediately to a safe distance")
    var minimum := INF
    var maximum := 0.0
    for i in range(120):
        var safe := 3.0 if i%2==0 else 7.0
        var eye: Vector3 = rig.constrain_arm(pivot,nominal,safe,1.0/60.0)
        minimum = minf(minimum,eye.length())
        maximum = maxf(maximum,eye.length())
        check(eye.length()<=safe+0.001,"Camera cannot cross the current obstruction")
    check(maximum-minimum<0.001,"Alternating brief clear gaps cannot pump the camera in and out")
    check(rig.position==nominal,"Collision output must not feed back into the nominal position filter")
    for i in range(20):
        rig.constrain_arm(pivot,nominal,7.0,1.0/60.0)
    check(absf(rig._arm_length-3.0)<0.001,"Release must wait for sustained clearance")
    for i in range(180):
        var before: float = rig._arm_length
        rig.constrain_arm(pivot,nominal,7.0,1.0/60.0)
        check(rig._arm_length-before<=2.0/60.0+0.001,"Clearance release must respect its metre-per-second cap")
    check(absf(rig._arm_length-7.0)<0.001,"Camera must eventually recover its original distance")
    var at_30 := release_at(30)
    var at_120 := release_at(120)
    check(absf(at_30-at_120)<0.08,"Release behaviour must remain consistent across frame rates")
    var reset_eye: Vector3 = rig.constrain_arm(pivot,nominal,5.0,0.0,true)
    check(absf(reset_eye.length()-5.0)<0.001,"Explicit camera reset must reset collision history")
    print("Contact camera alternating variation=",maximum-minimum," release_30=",at_30," release_120=",at_120)
    print("Camera contact smoke: ",failures," failures")
    quit(1 if failures else 0)
