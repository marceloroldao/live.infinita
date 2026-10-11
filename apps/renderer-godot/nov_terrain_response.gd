extends RefCounted
# Local geometric speed response; not a metabolic or material simulation.
const SAMPLE_M := 0.5
const GRADE_DEAD_ZONE := 0.03
func sample(current:Vector3,direction:Vector2,ground:Callable)->Dictionary:
    var value:Dictionary={"enabled":true,"source":"local_ground_geometry","sample_distance_m":SAMPLE_M,
        "grade":0.0,"speed_factor":1.0,"phase":"flat","sample_valid":true,"world_write_authority":false}
    if not current.is_finite() or not direction.is_finite() or not ground.is_valid():
        value.sample_valid=false;value.speed_factor=0.0;value.phase="unavailable";return value
    if direction.length_squared()<0.000001:return value
    var offset:=direction.normalized()*SAMPLE_M
    var a:Vector3=ground.call(current.x,current.z)
    var b:Vector3=ground.call(current.x+offset.x,current.z+offset.y)
    if not a.is_finite() or not b.is_finite():
        value.sample_valid=false;value.speed_factor=0.0;value.phase="unavailable";return value
    var grade:=clampf((b.y-a.y)/SAMPLE_M,-0.7,0.7)
    value.grade=grade
    if grade>GRADE_DEAD_ZONE:
        value.phase="uphill";value.speed_factor=1.0/(1.0+2.0*grade)
    elif grade < -GRADE_DEAD_ZONE:
        value.phase="downhill";value.speed_factor=1.0/(1.0+0.75*absf(grade))
    return value
