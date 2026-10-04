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

# Collision constrains output, not the nominal follow filter. A short clear gap
# cannot repeatedly expand/retract the eye around the edge of a trunk.
const ARM_RELEASE_DELAY := 0.6
const ARM_RELEASE_MPS := 2.0
var _arm_ready := false
var _arm_length := 0.0
var _arm_clear_time := 0.0

func constrain_arm(pivot: Vector3, nominal: Vector3, safe_distance: float, delta: float, reset: bool = false) -> Vector3:
    var dt := clampf(delta,0.0,0.1)
    var offset := nominal-pivot
    var desired := offset.length()
    var safe := clampf(safe_distance,0.0,desired)
    if not _arm_ready or reset:
        _arm_length = safe
        _arm_clear_time = 0.0
        _arm_ready = true
    if safe < _arm_length:
        # Retraction is immediate for physical safety.
        _arm_length = safe
        _arm_clear_time = 0.0
    elif safe < desired-0.01:
        _arm_clear_time = 0.0
    else:
        _arm_clear_time += dt
        if _arm_clear_time >= ARM_RELEASE_DELAY:
            _arm_length = move_toward(_arm_length,safe,ARM_RELEASE_MPS*dt)
    _arm_length = minf(_arm_length,safe)
    return pivot+offset.normalized()*_arm_length if desired>0.001 else pivot
