extends RefCounted
# Bounded small drops against the established terrain surface; no jumping.
const GRAVITY_MPS2 := 9.81
const MAX_FALL_SPEED_MPS := 8.0
const SNAP_DOWN_M := 0.08
const MAX_UP_STEP_M := 0.35
var vertical_speed := 0.0
var airborne := false
func reset() -> void:
    vertical_speed=0.0;airborne=false
func advance(height:float,ground:float,dt:float,follow_surface:bool=false)->Dictionary:
    if not is_finite(height) or not is_finite(ground) or not is_finite(dt) or dt<=0.0:
        return {"height":height,"grounded":not airborne,"vertical_speed":vertical_speed}
    dt=minf(dt,0.1)
    if height<=ground or (not airborne and (height-ground<=SNAP_DOWN_M or follow_surface)):
        reset();return {"height":ground,"grounded":true,"vertical_speed":0.0}
    airborne=true
    vertical_speed=maxf(-MAX_FALL_SPEED_MPS,vertical_speed-GRAVITY_MPS2*dt)
    var next:=maxf(ground,height+vertical_speed*dt)
    if next<=ground+0.00001:
        reset();return {"height":ground,"grounded":true,"vertical_speed":0.0}
    return {"height":next,"grounded":false,"vertical_speed":vertical_speed}
