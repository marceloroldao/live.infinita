extends RefCounted
# 008BR: visual-only distant relief. Never changes walkable terrain or World State.

const ENABLED := true
const START_M := 180.0
const FULL_M := 360.0
const SCALE := 1.55
const MAX_VISUAL_DELTA_M := 18.0

var _observer := Vector2.ZERO
var _reference_height := 0.0

func update_observer(position: Vector3, reference_height: float) -> void:
    _observer = Vector2(position.x, position.z)
    _reference_height = reference_height

func height_for(
    base_y: float,
    distance_m: float,
    reference_y: float,
) -> float:
    if not ENABLED or distance_m <= START_M:
        return base_y
    var span := maxf(1.0, FULL_M - START_M)
    var t := clampf((distance_m - START_M) / span, 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    var extra := (base_y - reference_y) * (SCALE - 1.0) * t
    extra = clampf(extra, -MAX_VISUAL_DELTA_M, MAX_VISUAL_DELTA_M)
    return base_y + extra

func visual_height(base_y: float, x: float, z: float) -> float:
    var distance_m := Vector2(x, z).distance_to(_observer)
    return height_for(base_y, distance_m, _reference_height)
