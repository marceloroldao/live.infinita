extends RefCounted
const CONFINED_SECONDS := 30.0
const NO_PROGRESS_SECONDS := 90.0
const CONFINED_RADIUS_M := 2.5
var anchor := Vector2.ZERO
var goal := Vector2.ZERO
var confined := 0.0
var no_progress := 0.0
var best_remaining := INF
var ready := false
func reset() -> void:
    ready = false
    confined = 0.0
    no_progress = 0.0
    best_remaining = INF
func observe(position: Vector3, target: Vector3, delta: float, attempting: bool) -> bool:
    if not attempting or not position.is_finite() or not target.is_finite():
        reset()
        return false
    var point := Vector2(position.x,position.z)
    var destination := Vector2(target.x,target.z)
    var remaining := point.distance_to(destination)
    if remaining <= 0.1:
        reset()
        return false
    if not ready or destination.distance_to(goal)>0.1:
        reset()
        ready = true
        goal = destination
        anchor = point
        best_remaining = remaining
    var dt := clampf(delta,0.0,0.25)
    confined += dt
    no_progress += dt
    if point.distance_to(anchor)>CONFINED_RADIUS_M:
        anchor = point
        confined = 0.0
    if remaining < best_remaining-1.0:
        best_remaining = remaining
        no_progress = 0.0
        confined = 0.0
        anchor = point
    return confined>=CONFINED_SECONDS or no_progress>=NO_PROGRESS_SECONDS
