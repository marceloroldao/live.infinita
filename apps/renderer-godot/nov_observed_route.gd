extends RefCounted
# Physically observed connections in a bounded 64 x 64 m window.
# No bridge coordinates or authoritative world access.
const CELL_M := 2.0
const RANGE_M := 32.0
const EXTENT := 16
const MAX_NODES := 1089
const NODES_PER_SLICE := 12
const SLICE_MS := 6
var sampled_edges := 0
var elapsed_ms := 0
var max_slice_ms := 0
var running := false
var _origin := Vector2.ZERO
var _goal := Vector2.ZERO
var _queue: Array[Vector2i] = []
var _parents: Dictionary = {}
var _best := Vector2i.ZERO
var _best_distance := INF
var _head := 0

func cancel() -> void:
    running = false
    _queue.clear()
    _parents.clear()

func advance(current: Vector2, goal: Vector2, probe: Callable) -> Array[Vector2]:
    var result: Array[Vector2] = []
    if not probe.is_valid(): return result
    if not running:
        _origin = current
        _goal = goal
        _queue = [Vector2i.ZERO]
        _parents = {Vector2i.ZERO:Vector2i.ZERO}
        _best = Vector2i.ZERO
        _best_distance = current.distance_to(goal)
        _head = 0
        sampled_edges = 0
        elapsed_ms = 0
        max_slice_ms = 0
        running = true
    var started := Time.get_ticks_msec()
    var processed := 0
    var offset := _goal-_origin
    var directions := [Vector2i.UP,Vector2i.DOWN,Vector2i.RIGHT,Vector2i.LEFT] if absf(offset.x)>=absf(offset.y) else [Vector2i.LEFT,Vector2i.RIGHT,Vector2i.UP,Vector2i.DOWN]
    while _head<_queue.size() and _head<MAX_NODES and processed<NODES_PER_SLICE:
        var cell := _queue[_head]
        _head += 1
        processed += 1
        var start := _origin + Vector2(cell)*CELL_M
        for direction in directions:
            var next: Vector2i = cell + direction
            if absi(next.x)>EXTENT or absi(next.y)>EXTENT or _parents.has(next): continue
            var point := _origin + Vector2(next)*CELL_M
            sampled_edges += 1
            if not bool(probe.call(start,point)): continue
            _parents[next] = cell
            _queue.append(next)
            var distance := point.distance_to(_goal)
            if distance<_best_distance-0.01:
                _best = next
                _best_distance = distance
        if Time.get_ticks_msec()-started>=SLICE_MS: break
    var spent := Time.get_ticks_msec()-started
    elapsed_ms += spent
    max_slice_ms = maxi(max_slice_ms,spent)
    if _head<_queue.size() and _head<MAX_NODES: return result
    running = false
    if _best_distance<_origin.distance_to(_goal)-0.5:
        var cursor := _best
        while cursor!=Vector2i.ZERO:
            result.push_front(_origin + Vector2(cursor)*CELL_M)
            cursor = _parents[cursor]
    return result

func build(current: Vector2, goal: Vector2, probe: Callable) -> Array[Vector2]:
    cancel()
    var result := advance(current,goal,probe)
    while running:
        result = advance(current,goal,probe)
    return result
