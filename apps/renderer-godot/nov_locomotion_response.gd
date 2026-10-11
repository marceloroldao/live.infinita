extends RefCounted
# Horizontal body response. Collision and terrain remain authoritative.
const ACCEL_MPS2 := 18.0
const BRAKE_MPS2 := 24.0
var velocity := Vector2.ZERO
func stop() -> void:
    velocity = Vector2.ZERO
func displacement(current: Vector2, waypoint: Vector2, goal: Vector2, speed: float, dt: float) -> Vector2:
    if not current.is_finite() or not waypoint.is_finite() or not goal.is_finite() or not is_finite(speed) or not is_finite(dt) or dt <= 0.0:
        stop(); return Vector2.ZERO
    dt = minf(dt, 0.1)
    var offset := waypoint-current
    var remaining := goal.distance_to(current)
    if offset.length() < 0.001 or remaining < 0.04:
        stop(); return Vector2.ZERO
    var limit := minf(maxf(speed,0.0),sqrt(2.0*BRAKE_MPS2*remaining))
    var direction := offset.normalized()
    # Brake before sharp turns. Seeking a nearby waypoint at full speed
    # otherwise makes the capsule orbit it under bounded acceleration.
    if velocity.length()>0.3:
        limit *= maxf(0.0,velocity.normalized().dot(direction))
    var desired := direction*limit
    var braking := desired.length()<velocity.length() or velocity.dot(desired)<0.0
    velocity = velocity.move_toward(desired,(BRAKE_MPS2 if braking else ACCEL_MPS2)*dt)
    var move := velocity*dt
    # Prevent overshoot of the local navigation waypoint.
    if move.length()>offset.length():
        move = move.normalized()*offset.length()
        velocity = move/dt
    return move
func executed(move: Vector2, dt: float, collision: bool) -> void:
    if collision or dt<=0.0:
        stop()
    else:
        velocity = move/minf(dt,0.1)
