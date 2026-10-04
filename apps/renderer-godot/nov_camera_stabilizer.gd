extends RefCounted
# Camera inertia is independent of NOV's navigation and animation.
const TURN_RATE_RAD := PI / 4.0
const TURN_HOLD_SECONDS := 0.25
const CANDIDATE_TOLERANCE_RAD := PI / 5.0
const HEADING_DEAD_ZONE_RAD := PI / 22.5
const POSITION_RATE := 7.0
const HEIGHT_RATE := 3.0
const LOOK_RATE := 5.0

var _heading_ready := false
var _candidate_yaw := 0.0
var _candidate_time := 0.0
var _pose_ready := false
var position := Vector3.ZERO
var target := Vector3.ZERO

func observe_motion(previous: Vector3, current: Vector3, delta: float, forward: Vector3) -> Vector3:
    var dt := clampf(delta, 0.0, 0.1)
    var motion := Vector2(current.x - previous.x, current.z - previous.z)
    if motion.length() < 0.002:
        return forward
    var desired := atan2(motion.x, motion.y)
    var yaw := atan2(forward.x, forward.z)
    if not _heading_ready:
        _candidate_yaw = desired
        _candidate_time = 0.0
        _heading_ready = true
    elif absf(angle_difference(_candidate_yaw, desired)) > CANDIDATE_TOLERANCE_RAD:
        _candidate_yaw = desired
        _candidate_time = 0.0
    else:
        _candidate_yaw = lerp_angle(_candidate_yaw, desired, 1.0 - exp(-6.0 * dt))
    _candidate_time += dt
    if _candidate_time < TURN_HOLD_SECONDS:
        return forward
    var difference := angle_difference(yaw, _candidate_yaw)
    if absf(difference) < HEADING_DEAD_ZONE_RAD:
        return forward
    yaw += clampf(difference, -TURN_RATE_RAD * dt, TURN_RATE_RAD * dt)
    return Vector3(sin(yaw), 0.0, cos(yaw))

func follow(desired_position: Vector3, desired_target: Vector3, delta: float, reset: bool = false) -> void:
    var dt := clampf(delta, 0.0, 0.1)
    if not _pose_ready or reset:
        position = desired_position
        target = desired_target
        _pose_ready = true
        return
    position.x = lerpf(position.x, desired_position.x, 1.0 - exp(-POSITION_RATE * dt))
    position.z = lerpf(position.z, desired_position.z, 1.0 - exp(-POSITION_RATE * dt))
    position.y = lerpf(position.y, desired_position.y, 1.0 - exp(-HEIGHT_RATE * dt))
    target = target.lerp(desired_target, 1.0 - exp(-LOOK_RATE * dt))
